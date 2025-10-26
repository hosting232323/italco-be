import os
import io
import json
from api.sms import send_sms
from datetime import datetime
from flask import Blueprint, request, send_file

from ... import IS_DEV
from .mailer import mailer_check
from api import error_catching_decorator
from ..users.session import flask_session_authentication
from ..schedule import get_selling_point, get_order_link
from ...database.schema import User, Order, Photo, Motivation
from ...database.enum import OrderStatus, UserRole, OrderType
from database_api.operations import create, update, get_by_id
from .services import create_order_service_user, update_order_service_user
from .queries import (
  query_orders,
  query_delivery_orders,
  format_query_result,
  get_delivery_user_by_schedule_id,
  get_order_photo_ids,
  get_motivations_by_order_id,
)


order_bp = Blueprint('order_bp', __name__)


# TODO CHECK ELIMINAZIONI RELAZIONI N A N
@order_bp.route('', methods=['POST'])
@flask_session_authentication([UserRole.CUSTOMER, UserRole.OPERATOR, UserRole.ADMIN])
def create_order(user: User):
  data = {key: value for key, value in request.json.items() if key not in ['products', 'user_id']}
  data['type'] = OrderType.get_enum_option(data['type'])
  order = create(Order, data)
  create_order_service_user(
    order, request.json['products'], user.id if user.role == UserRole.CUSTOMER else request.json['user_id']
  )
  return {'status': 'ok', 'order': order.to_dict()}


@order_bp.route('delivery', methods=['GET'])
@flask_session_authentication([UserRole.DELIVERY])
def get_orders_for_delivery(user: User):
  orders = []
  for tupla in query_delivery_orders(user):
    orders = format_query_result(tupla, orders, user)
  response = {}
  for order in orders:
    if order['status'] not in response:
      response[order['status']] = []
    response[order['status']].append(order)
  return {'status': 'ok', 'orders': response}


@order_bp.route('filter', methods=['POST'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN, UserRole.CUSTOMER])
def filter_orders(user: User):
  orders = []
  for tupla in query_orders(user, request.json['filters']):
    orders = format_query_result(tupla, orders, user)
  return {'status': 'ok', 'orders': orders}


@order_bp.route('<id>', methods=['GET'])
@error_catching_decorator
def get_order(id):
  user = User(role=UserRole.DELIVERY)
  orders = []
  for tupla in query_orders(user, [{'model': 'Order', 'field': 'id', 'value': int(id)}]):
    orders = format_query_result(tupla, orders, user)
  if len(orders) != 1:
    raise Exception('Numero di ordini trovati non valido')

  order = orders[0]
  if order['status'] == 'On Board':
    user = get_delivery_user_by_schedule_id(order['schedule_id'])
    if user.lat is not None and user.lon is not None:
      order['lat'] = user.lat
      order['lon'] = user.lon

  return {'status': 'ok', 'order': order}


@order_bp.route('<id>', methods=['PUT'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.DELIVERY, UserRole.ADMIN, UserRole.CUSTOMER])
def update_order(user: User, id):
  order: Order = get_by_id(Order, int(id))
  if user.role in [UserRole.DELIVERY, UserRole.ADMIN] and isinstance(request.form.get('data'), str):
    data = json.loads(request.form.get('data'))
    for file_key in request.files.keys():
      uploaded_file = request.files[file_key]
      if uploaded_file.mimetype in ['image/jpeg', 'image/png']:
        if file_key == 'signature':
          data['signature'] = uploaded_file.read()
        else:
          create(Photo, {'photo': uploaded_file.read(), 'mime_type': uploaded_file.mimetype, 'order_id': order.id})
  else:
    data = request.json

  if 'motivation' in data:
    motivation = create(
      Motivation,
      {
        'id_order': data['id'],
        'status': OrderStatus(data['status']),
        'delay': data['delay'] if 'delay' in data else False,
        'anomaly': data['anomaly'] if 'delay' in data else False,
        'text': data['motivation'],
      },
    )
  else:
    motivation = None

  data['type'] = OrderType.get_enum_option(data['type'])
  data['status'] = OrderStatus.get_enum_option(data['status'])
  if data['status'] in [OrderStatus.CANCELLED, OrderStatus.COMPLETED]:
    data['booking_date'] = datetime.now()
  if user.role != UserRole.DELIVERY:
    update_order_service_user(order, data['products'], user.id if user.role == UserRole.CUSTOMER else data['user_id'])

  previous_start = order.start_time_slot
  previous_end = order.end_time_slot
  data = {key: value for key, value in data.items() if key not in ['products', 'user_id', 'motivation']}
  order = update(order, data)

  if (
    not IS_DEV
    and 'delay' in data
    and data['delay']
    and order.addressee_contact
    and (parse_time(data['start_time_slot']) != previous_start or parse_time(data['end_time_slot']) != previous_end)
  ):
    start = order.start_time_slot.strftime('%H:%M')
    end = order.end_time_slot.strftime('%H:%M')
    send_sms(
      os.environ['VONAGE_API_KEY'],
      os.environ['VONAGE_API_SECRET'],
      'Ares',
      order.addressee_contact,
      f'ARES ITALCO.MI - Gentile Cliente, la consegna relativa al Punto Vendita: {get_selling_point(order)}, è stata riprogrammata per il {order.assignament_date}'
      f", fascia {start} - {end}. Riceverà un preavviso di 30 minuti prima dell'arrivo. Per monitorare ogni fase della sua consegna clicchi il link in question"
      f'e {get_order_link(order)}. La preghiamo di garantire la presenza e la reperibilità al numero indicato. Buona Giornata!',
    )

  mailer_check(order, data, motivation)
  return {'status': 'ok', 'order': order.to_dict()}


@order_bp.route('delivery-details/<order_id>', methods=['GET'])
@error_catching_decorator
@flask_session_authentication([UserRole.OPERATOR, UserRole.CUSTOMER, UserRole.ADMIN])
def get_delivery_details(user: User, order_id: int):
  return {
    'status': 'ok',
    'motivations': [m.to_dict() for m in get_motivations_by_order_id(order_id)],
    'photos': get_order_photo_ids(order_id),
  }


@order_bp.route('photo/<photo_id>', methods=['GET'])
@error_catching_decorator
def view_order_photo(photo_id: int):
  photo: Photo = get_by_id(Photo, photo_id)
  if not photo:
    return {'status': 'ko', 'error': 'Photo not found'}

  return send_file(
    io.BytesIO(photo.photo),
    mimetype=photo.mime_type or 'application/octet-stream',
    as_attachment=False,
    download_name=f'order_photo_{photo_id}.jpg',
  )


def parse_time(value: str):
  for fmt in ['%H:%M', '%H:%M:%S']:
    try:
      return datetime.strptime(value, fmt).time()
    except ValueError:
      continue
  raise ValueError(f'Formato orario non riconosciuto: {value}')

import os
import io
import json
from api.sms import send_sms
from datetime import datetime
from flask import Blueprint, request, send_file

from .mailer import mailer_check
from api import error_catching_decorator
from .. import flask_session_authentication
from ...database.schema import ItalcoUser, Order, Photo
from ..schedule import get_selling_point, get_order_link
from ...database.enum import OrderStatus, UserRole, OrderType
from database_api.operations import create, update, get_by_id
from .services import create_order_service_user, update_order_service_user
from .queries import query_orders, query_delivery_orders, format_query_result, query_delivery_group

order_bp = Blueprint('order_bp', __name__)


# TODO CHECK ELIMINAZIONI RELAZIONI N A N
@order_bp.route('', methods=['POST'])
@flask_session_authentication([UserRole.CUSTOMER, UserRole.OPERATOR, UserRole.ADMIN])
def create_order(user: ItalcoUser):
  data = {key: value for key, value in request.json.items() if key not in ['products', 'user_id']}
  data['type'] = OrderType.get_enum_option(data['type'])
  order = create(Order, data)
  create_order_service_user(
    order, request.json['products'], user.id if user.role == UserRole.CUSTOMER else request.json['user_id']
  )
  return {'status': 'ok', 'order': order.to_dict()}


@order_bp.route('delivery', methods=['GET'])
@flask_session_authentication([UserRole.DELIVERY])
def get_orders_for_delivery(user: ItalcoUser):
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
def filter_orders(user: ItalcoUser):
  orders = []
  for tupla in query_orders(user, request.json['filters'], request.json['date_filter']):
    orders = format_query_result(tupla, orders, user)
  return {'status': 'ok', 'orders': orders}


@order_bp.route('<id>', methods=['GET'])
@error_catching_decorator
def get_order(id):
  user = ItalcoUser(role=UserRole.DELIVERY)
  orders = []
  for tupla in query_orders(user, [{'model': 'Order', 'field': 'id', 'value': int(id)}]):
    orders = format_query_result(tupla, orders, user)
  if len(orders) != 1:
    raise Exception('Numero di ordini trovati non valido')

  order = orders[0]
  if order['status'] == 'On Board':
    delivery_group = query_delivery_group(order['schedule_id'])
    if delivery_group.lat is not None and delivery_group.lon is not None:
      order['lat'] = delivery_group.lat
      order['lon'] = delivery_group.lon

  return {'status': 'ok', 'order': order}


@order_bp.route('<id>', methods=['PUT'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.DELIVERY, UserRole.ADMIN, UserRole.CUSTOMER])
def update_order(user: ItalcoUser, id):
  order: Order = get_by_id(Order, int(id))
  if user.role == UserRole.DELIVERY:
    data = json.loads(request.form.get('data'))
    for file in request.files.keys():
      if request.files[file].mimetype in ['image/jpeg', 'image/png']:
        create(
          Photo, {'photo': request.files[file].read(), 'mime_type': request.files[file].mimetype, 'order_id': order.id}
        )
  else:
    data = request.json

  data['type'] = OrderType.get_enum_option(data['type'])
  data['status'] = OrderStatus.get_enum_option(data['status'])
  if user.role == UserRole.DELIVERY and data['status'] in [OrderStatus.CANCELLED, OrderStatus.COMPLETED]:
    data['booking_date'] = datetime.now()
  if user.role != UserRole.DELIVERY:
    update_order_service_user(order, data['products'], user.id if user.role == UserRole.CUSTOMER else data['user_id'])

  previous_start = order.start_time_slot
  previous_end = order.end_time_slot
  data = {key: value for key, value in data.items() if key not in ['products', 'user_id']}
  order = update(order, data)

  if (
    'delay' in data
    and data['delay']
    and order.addressee_contact
    and (
      datetime.strptime(data['start_time_slot'], '%H:%M:%S').time() != previous_start
      or datetime.strptime(data['end_time_slot'], '%H:%M:%S').time() != previous_end
    )
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

  mailer_check(order, data)
  return {'status': 'ok', 'order': order.to_dict()}


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

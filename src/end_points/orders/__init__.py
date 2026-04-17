import os
import json
from datetime import datetime
from flask import Blueprint, request, send_from_directory

from database_api import Session
from .mailer import mailer_check
from .photo import handle_photos
from ... import STATIC_FOLDER, IS_DEV
from .sms_sender import delay_sms_check
from api import error_catching_decorator
from ..users.queries import get_user_info
from .api import save_order_status_to_euronics
from ..service.queries import get_service_users
from .services import create_products, update_products
from .utils import parse_time, get_statuses_by_order_id
from ..users.session import flask_session_authentication
from ...database.enum import OrderStatus, UserRole, OrderType
from database_api.operations import create, update, get_by_id, delete
from ...database.schema import User, Order, Motivation, ServiceUser, DeliveryUserInfo
from ..schedule.queries import get_schedule_item_by_order, get_delivery_groups_by_order_id
from .queries import (
  query_orders,
  format_query_result,
  get_order_photos,
  get_motivations_by_order_id,
  query_products,
)


order_bp = Blueprint('order_bp', __name__)


# TODO CHECK ELIMINAZIONI RELAZIONI N A N
@order_bp.route('', methods=['POST'])
@flask_session_authentication([UserRole.CUSTOMER, UserRole.OPERATOR, UserRole.ADMIN])
def create_order(user: User):
  data = {key: value for key, value in request.json.items() if key not in ['products', 'user_id', 'cloned_order_id']}
  data['type'] = OrderType(data['type'])
  if user.role in [UserRole.ADMIN, UserRole.OPERATOR]:
    data['confirmed'] = True
    data['confirmation_date'] = datetime.now()
    if 'booking_date' in data and data['booking_date'] is not None:
      data['status'] = OrderStatus.BOOKED

  with Session() as session:
    order: Order = create(Order, data, session=session)
    create_products(
      order,
      request.json['products'],
      user.id if user.role == UserRole.CUSTOMER else request.json['user_id'],
      session=session,
    )

    if 'cloned_order_id' in request.json and request.json['cloned_order_id']:
      cloned_order: Order = get_by_id(Order, request.json['cloned_order_id'], session=session)
      new_note = f"Rischedulato con l'ordine {order.id}"
      update(
        cloned_order,
        {
          'completion_date': datetime.now(),
          'status': OrderStatus.REDELIVERY,
          'operator_note': f'{new_note}, {cloned_order.operator_note}' if cloned_order.operator_note else new_note,
        },
        session=session,
      )
      new_note = f'Clonato da ordine {request.json["cloned_order_id"]}'
      update(
        order,
        {'operator_note': f'{new_note}, {data["operator_note"]}' if 'operator_note' in data else new_note},
        session=session,
      )

    session.commit()
    save_order_status_to_euronics(order)
  return {'status': 'ok', 'order': order.to_dict()}


@order_bp.route('filter', methods=['POST'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN, UserRole.CUSTOMER])
def filter_orders(user: User):
  orders = []
  for tupla in query_orders(user, request.json['filters'], 500):
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

  if orders[0]['status'] == 'Booking':
    for delivery_group in get_delivery_groups_by_order_id(orders[0]['id']):
      delivery_user_info = get_user_info(delivery_group.user_id, DeliveryUserInfo)
      if delivery_user_info and delivery_user_info.lat is not None and delivery_user_info.lon is not None:
        orders[0]['lat'] = delivery_user_info.lat
        orders[0]['lon'] = delivery_user_info.lon
        break

  return {'status': 'ok', 'order': orders[0]}


@order_bp.route('<id>', methods=['PUT'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.DELIVERY, UserRole.ADMIN, UserRole.CUSTOMER])
def update_order(user: User, id):
  with Session() as session:
    order: Order = get_by_id(Order, int(id), session=session)
    if isinstance(request.form.get('data'), str):
      data = handle_photos(json.loads(request.form.get('data')), order, session=session)
    else:
      data = request.json

    is_delay = data['delay'] if 'delay' in data else False
    if 'motivation' in data:
      motivation = create(
        Motivation,
        {
          'delay': is_delay,
          'order_id': data['id'],
          'status': OrderStatus(data['status']),
          'anomaly': data['anomaly'] if 'delay' in data else False,
          'text': data['motivation'],
        },
        session=session,
      )
    else:
      motivation = None

    if 'type' in data:
      data['type'] = OrderType(data['type'])
    if 'status' in data:
      data['status'] = OrderStatus(data['status'])
      if data['status'] in [OrderStatus.NOT_DELIVERED, OrderStatus.DELIVERED] and not order.completion_date:
        data['completion_date'] = datetime.now()
      if data['status'] in [OrderStatus.NOT_DELIVERED, OrderStatus.DELIVERED, OrderStatus.TO_RESCHEDULE]:
        schedule_item = get_schedule_item_by_order(order)
        if schedule_item:
          update(schedule_item, {'completed': True}, session=session)
    if 'confirmed' in data and data['confirmed'] and not order.confirmation_date:
      data['confirmation_date'] = datetime.now()
    if 'external_status' in data:
      del data['external_status']
    if user.role != UserRole.DELIVERY and 'products' in data:
      update_products(order, data['products'], user.id if user.role == UserRole.CUSTOMER else data['user_id'], session)

    if order.status == OrderStatus.ACQUIRED and 'booking_date' in data and order.booking_date != data['booking_date']:
      data['status'] = OrderStatus.BOOKED

    if is_delay and 'start_time_slot' in data and 'end_time_slot' in data:
      schedule_item = get_schedule_item_by_order(order)
      if (
        parse_time(data['start_time_slot']) != schedule_item.start_time_slot
        or parse_time(data['end_time_slot']) != schedule_item.end_time_slot
      ):
        update(
          schedule_item,
          {'start_time_slot': data['start_time_slot'], 'end_time_slot': data['end_time_slot']},
          session=session,
        )
        delay_sms_check(order, data)

    data = {
      key: value
      for key, value in data.items()
      if key not in ['products', 'user_id', 'motivation', 'start_time_slot', 'end_time_slot']
    }
    order = update(order, data, session=session)

    session.commit()
    save_order_status_to_euronics(order)
    mailer_check(order, data, motivation)
  return {'status': 'ok', 'order': order.to_dict()}


@order_bp.route('customer', methods=['POST'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
def update_order_customer(user: User):
  updates = []
  service_users = get_service_users(request.json['user_id'])
  products = query_products(get_by_id(Order, request.json['order_id']))
  for product in products:
    old_service_user: ServiceUser = get_by_id(ServiceUser, product.service_user_id)
    service_user = next(
      (service_user for service_user in service_users if service_user.service_id == old_service_user.service_id), None
    )
    if service_user:
      updates.append((product, service_user))
  if len(updates) != len(products):
    return {'status': 'ko', 'error': "Il nuovo utente non possiete gli stessi servizi dell'utente precedente"}

  for product, service_user in updates:
    update(product, {'service_user_id': service_user.id})
  return {'status': 'ok', 'message': 'Operazione completata'}


@order_bp.route('delivery-details/<order_id>', methods=['GET'])
@error_catching_decorator
@flask_session_authentication([UserRole.OPERATOR, UserRole.CUSTOMER, UserRole.ADMIN])
def get_delivery_details(user: User, order_id: int):
  return {
    'status': 'ok',
    'motivations': [m.to_dict() for m in get_motivations_by_order_id(order_id)],
    'photos': [photo.link for photo in get_order_photos(order_id)],
  }


@order_bp.route('<id>', methods=['DELETE'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN])
def delete_order(user: User, id):
  order: Order = get_by_id(Order, int(id))
  item = get_schedule_item_by_order(order)
  if not order or item or order.status not in [OrderStatus.ACQUIRED, OrderStatus.BOOKED]:
    return {
      'status': 'ko',
      'error': "Si necessità un ordine in stato di attesa senza borderò per procedere con l'eliminazione",
    }

  delete(order)
  return {'status': 'ok', 'message': 'Operazione completata'}


@order_bp.route('get-statuses/<id>', methods=['GET'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
def get_statuses(user: User, id):
  return get_statuses_by_order_id(id)


@order_bp.route('photos/<filename>', methods=['GET'])
@error_catching_decorator
def serve_image(filename):
  if IS_DEV:
    folder = os.path.join(STATIC_FOLDER, 'test')
  else:
    folder = os.path.join(STATIC_FOLDER, 'prod')
  return send_from_directory(folder, filename)

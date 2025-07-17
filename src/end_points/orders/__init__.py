import io
import json
from datetime import datetime
from flask import Blueprint, request, send_file

from .mailer import mailer_check
from api import error_catching_decorator
from .. import flask_session_authentication
from ...database.schema import ItalcoUser, Order, Photo, CollectionPoint, OrderServiceUser
from ...database.enum import OrderStatus, UserRole, OrderType
from database_api.operations import create, update, get_by_id
from .services import create_order_service_user, update_order_service_user
from .queries import query_orders, query_delivery_orders, format_query_result
from database_api import Session


order_bp = Blueprint('order_bp', __name__)


# TODO CHECK ELIMINAZIONI RELAZIONI N A N
@order_bp.route('', methods=['POST'])
@error_catching_decorator
@flask_session_authentication([UserRole.CUSTOMER, UserRole.OPERATOR, UserRole.ADMIN])
def create_order(user: ItalcoUser):
  data = {key: value for key, value in request.json.items() if not key in ['products', 'user_id']}
  data['type'] = OrderType.get_enum_option(data['type'])
  order = create(Order, data)
  create_order_service_user(
    order,
    request.json['products'],
    user.id if user.role == UserRole.CUSTOMER else request.json['user_id']
  )
  return {
    'status': 'ok',
    'order': order.to_dict()
  }


@order_bp.route('delivery', methods=['GET'])
@error_catching_decorator
@flask_session_authentication([UserRole.DELIVERY])
def get_orders_for_delivery(user: ItalcoUser):
  orders = []
  for tupla in query_delivery_orders(user):
    orders = format_query_result(tupla, orders, user)
  response = {}
  for order in orders:
    if not order['status'] in response:
      response[order['status']] = []
    response[order['status']].append(order)
  return {
    'status': 'ok',
    'orders': response
  }


@order_bp.route('filter', methods=['POST'])
@error_catching_decorator
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN, UserRole.CUSTOMER])
def filter_orders(user: ItalcoUser):
  orders = []
  for tupla in query_orders(user, request.json['filters'], request.json['date_filter']):
    orders = format_query_result(tupla, orders, user)
  return {
    'status': 'ok',
    'orders': orders
  }


@order_bp.route('<id>', methods=['GET'])
@error_catching_decorator
def get_order(id):
  user = ItalcoUser(role=UserRole.DELIVERY)
  order = []
  for tupla in query_orders(user, [{
    'model': 'Order',
    'field': 'id',
    'value': int(id)
  }]):
    order = format_query_result(tupla, order, user)
  if len(order) != 1:
    raise Exception('Numero di ordini trovati non valido')
  
  return {
    'status': 'ok',
    'order': order[0]
  }


@order_bp.route('<id>', methods=['PUT'])
@error_catching_decorator
@flask_session_authentication([UserRole.OPERATOR, UserRole.DELIVERY, UserRole.ADMIN, UserRole.CUSTOMER])
def update_order(user: ItalcoUser, id):
  order: Order = get_by_id(Order, int(id))
  if user.role == UserRole.DELIVERY:
    data = json.loads(request.form.get('data'))
    for file in request.files.keys():
      if request.files[file].mimetype in ['image/jpeg', 'image/png']:
        create(Photo, {
          'photo': request.files[file].read(),
          'mime_type': request.files[file].mimetype,
          'order_id': order.id
        })
  else:
    data = request.json

  data['type'] = OrderType.get_enum_option(data['type'])
  data['status'] = OrderStatus.get_enum_option(data['status'])

  if user.role == UserRole.DELIVERY and data['status'] in [OrderStatus.ANOMALY, OrderStatus.CANCELLED, OrderStatus.COMPLETED]:
    data['booking_date'] = datetime.now()
  if user.role != UserRole.DELIVERY:
    update_order_service_user(
      order,
      data['products'],
      user.id if user.role == UserRole.CUSTOMER else data['user_id']
    )
  data = {key: value for key, value in data.items() if not key in ['products', 'user_id']}
  order = update(order, data)

  mailer_check(order)
  return {
    'status': 'ok',
    'order': order.to_dict()
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
    download_name=f'order_photo_{photo_id}.jpg'
  )

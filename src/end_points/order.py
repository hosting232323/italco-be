import io
import json
from datetime import datetime
from sqlalchemy import and_, not_
from flask import Blueprint, request, send_file

from ..database.schema import *
from database_api import Session
from api import error_catching_decorator
from . import flask_session_authentication
from ..database.enum import OrderStatus, UserRole, OrderType
from database_api.operations import create, update, get_by_id, delete

from api.email import send_email


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
  
  if data['status'] in [OrderStatus.ANOMALY, OrderStatus.CANCELLED, OrderStatus.COMPLETED]:
    subject = f'Ordine di tipo: {data['status']}'
    body = f"Ordine: {order.id} aggiornato"
    send_email('operatori@italco.it', body, subject)
    
  if user.role == UserRole.DELIVERY and data['status'] in [OrderStatus.ANOMALY, OrderStatus.CANCELLED, OrderStatus.COMPLETED]:
    data['booking_date'] = datetime.now()
  if user.role != UserRole.DELIVERY:
    update_order_service_user(
      order,
      data['products'],
      user.id if user.role == UserRole.CUSTOMER else data['user_id']
    )
  data = {key: value for key, value in data.items() if not key in ['products', 'user_id']}

  return {
    'status': 'ok',
    'order': update(order, data).to_dict()
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


def query_orders(user: ItalcoUser, filters: list, date_filter = {}) -> list[tuple[
  Order, OrderServiceUser, ServiceUser, Service, ItalcoUser, CollectionPoint, Photo
]]:
  with Session() as session:
    query = session.query(
      Order, OrderServiceUser, ServiceUser, Service, ItalcoUser, CollectionPoint, Photo
    ).outerjoin(
      CollectionPoint, Order.collection_point_id == CollectionPoint.id
    ).outerjoin(
      OrderServiceUser, OrderServiceUser.order_id == Order.id
    ).outerjoin(
      ServiceUser, OrderServiceUser.service_user_id == ServiceUser.id
    ).outerjoin(
      Service, ServiceUser.service_id == Service.id
    ).outerjoin(
      ItalcoUser, ServiceUser.user_id == ItalcoUser.id
    ).outerjoin(
      Photo, Photo.order_id == Order.id
    )

    if user.role == UserRole.CUSTOMER:
      query = query.filter(
        ItalcoUser.id == user.id
      )

    for filter in filters:
      if filter['model'] == 'Schedule':
        query = query.outerjoin(
          Schedule, Schedule.id == Order.schedule_id
        )
      elif filter['model'] == 'CustomerGroup':
        query = query.outerjoin(
          CustomerGroup, CustomerGroup.id == ItalcoUser.customer_group_id
        )
      elif filter['model'] == 'DeliveryGroup':
        query = query.outerjoin(
          Schedule, Schedule.id == Order.schedule_id
        ).outerjoin(
          DeliveryGroup, DeliveryGroup.id == Schedule.delivery_group_id
        )

      query = query.filter(getattr(globals()[filter['model']], filter['field']) == filter['value'])

    if date_filter != {}:
      query = query.filter(
        Order.booking_date >= datetime.strptime(date_filter['start_date'], '%Y-%m-%d'),
        Order.booking_date <= datetime.strptime(date_filter['end_date'], '%Y-%m-%d')
      )

    return query.all()


def query_delivery_orders(user: ItalcoUser) -> list[tuple[Order, OrderServiceUser, ServiceUser, Service, ItalcoUser, CollectionPoint, Photo]]:
  with Session() as session:
    return session.query(
      Order, OrderServiceUser, ServiceUser, Service, ItalcoUser, CollectionPoint, Photo
    ).outerjoin(
      CollectionPoint, Order.collection_point_id == CollectionPoint.id
    ).outerjoin(
      OrderServiceUser, OrderServiceUser.order_id == Order.id
    ).outerjoin(
      ServiceUser, OrderServiceUser.service_user_id == ServiceUser.id
    ).outerjoin(
      Service, ServiceUser.service_id == Service.id
    ).outerjoin(
      ItalcoUser, ServiceUser.user_id == ItalcoUser.id
    ).outerjoin(
      Photo, Photo.order_id == Order.id
    ).join(
      Schedule, and_(
        Schedule.delivery_group_id == user.delivery_group_id,
        Schedule.date == datetime.now().date(),
        Schedule.id == Order.schedule_id,
        not_(Order.status.in_([OrderStatus.PENDING, OrderStatus.COMPLETED, OrderStatus.CANCELLED]))
      )
    ).all()


def query_order_service_users(order: Order) -> list[OrderServiceUser]:
  with Session() as session:
    return session.query(OrderServiceUser).filter(
      OrderServiceUser.order_id == order.id
    ).all()


def query_service_users(service_ids: list[int], user_id: int, type: OrderType) -> list[ServiceUser]:
  with Session() as session:
    return session.query(ServiceUser).join(
      Service, Service.id == ServiceUser.service_id
    ).filter(
      ServiceUser.user_id == user_id,
      ServiceUser.service_id.in_(service_ids),
      Service.type == type
    ).all()


def format_query_result(tupla: tuple[
  Order, OrderServiceUser, ServiceUser, Service, ItalcoUser, CollectionPoint, Photo
], list: list[dict], user: ItalcoUser) -> list[dict]:
  for element in list:
    if element['id'] == tupla[0].id:
      add_photo(element, tupla[6])
      add_service(element, tupla[3], tupla[1], tupla[2].price)
      return list

  output = {
    **tupla[0].to_dict(),
    'price': 0,
    'photos': [],
    'products': {},
    'collection_point': tupla[5].to_dict(),
    'user': tupla[4].format_user(user.role)
  }
  add_photo(output, tupla[6])
  add_service(output, tupla[3], tupla[1], tupla[2].price)
  list.append(output)
  return list


def add_service(object: dict, service: Service, order_service_user: OrderServiceUser, price: float) -> dict:
  if not order_service_user.product in object['products'].keys():
    object['products'][order_service_user.product] = []

  if next((s for s in object['products'][order_service_user.product] if s['order_service_user_id'] == order_service_user.id), None):
    return object

  object['price'] += price
  object['products'][order_service_user.product].append(service.to_dict())
  object['products'][order_service_user.product][-1]['order_service_user_id'] = order_service_user.id
  return object


def add_photo(object: dict, photo: Photo) -> dict:
  if not photo or photo.id in object['photos']:
    return object

  object['photos'].append(photo.id)
  return object


def create_order_service_user(order: Order, products: dict, user_id: int):
  service_users = query_service_users(
    list(set(id for services in products.values() for id in services)),
    user_id,
    order.type
  )
  for product in products.keys():
    for service_id in products[product]:
      for service_user in service_users:
        if service_user.service_id == service_id:
          create(OrderServiceUser, {
            'order_id': order.id,
            'service_user_id': service_user.id,
            'product': product
          })
          break


def update_order_service_user(order: Order, products: dict, user_id: int):
  service_users = query_service_users(
    list(set(id for services in products.values() for id in services)),
    user_id,
    order.type
  )
  order_service_users = query_order_service_users(order)

  for product in products.keys():
    if len([
      order_service_user for order_service_user in order_service_users if order_service_user.product == product
    ]) > 0:
      continue

    for service_id in products[product]:
      for service_user in service_users:
        if service_user.service_id == service_id:
          create(OrderServiceUser, {
            'order_id': order.id,
            'service_user_id': service_user.id,
            'product': product
          })
        break

  for product in list({
    order_service_user.product for order_service_user in order_service_users
  }):
    for order_service_user in [
      order_service_user for order_service_user in order_service_users if order_service_user.product == product
    ]:
      if not order_service_user.product in products:
        delete(order_service_user)

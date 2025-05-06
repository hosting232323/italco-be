import io
import json
from datetime import datetime
from flask import Blueprint, request, send_file

from database_api import Session
from ..database.enum import OrderStatus, UserRole, OrderType
from . import error_catching_decorator, flask_session_authentication
from database_api.operations import create, update, get_by_id, get_by_ids
from ..database.schema import Order, ItalcoUser, Service, ServiceUser, DeliveryGroup, CollectionPoint, \
  Product, OrderServiceUser, OrderProduct, Addressee


order_bp = Blueprint('order_bp', __name__)


# TODO CHECK ELIMINAZIONI RELAZIONI N A N
@order_bp.route('', methods=['POST'])
@error_catching_decorator
@flask_session_authentication([UserRole.CUSTOMER, UserRole.OPERATOR, UserRole.ADMIN])
def create_order(user: ItalcoUser):
  request.json['type'] = OrderType.get_enum_option(request.json['type'])
  service_ids = request.json['service_ids']
  service_users = query_service_users(service_ids, user)
  products: list[Product] = get_by_ids(Product, request.json['product_ids'])
  if 'user_id' in request.json:
    del request.json['user_id']
  del request.json['service_ids']
  del request.json['product_ids']

  order = create(Order, request.json)
  for service_id in service_ids:
    for service_user in service_users:
      if service_user.service_id == service_id:
        create(OrderServiceUser, {
          'order_id': order.id,
          'service_user_id': service_user.id
        })
        break
  for product in products:
    create(OrderProduct, {
      'order_id': order.id,
      'product_id': product.id
    })
  return {
    'status': 'ok',
    'order': order.to_dict()
  }


@order_bp.route('filter', methods=['POST'])
@error_catching_decorator
@flask_session_authentication([UserRole.OPERATOR, UserRole.DELIVERY, UserRole.ADMIN, UserRole.CUSTOMER])
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
@flask_session_authentication([UserRole.OPERATOR, UserRole.DELIVERY])
def update_order(user: ItalcoUser, id):
  order: Order = get_by_id(Order, int(id))
  if user.role == UserRole.DELIVERY:
    data = json.loads(request.form.get('data'))
    file = request.files.get('photo')
    if file and file.mimetype in ['image/jpeg', 'image/png']:
      data['photo'] = file.read()
      data['photo_mime_type'] = file.mimetype
  else:
    data = request.json

  data['type'] = OrderType.get_enum_option(data['type'])
  data['status'] = OrderStatus.get_enum_option(data['status'])
  if user.role == UserRole.DELIVERY and data['status'] in [OrderStatus.ANOMALY, OrderStatus.CANCELLED, OrderStatus.COMPLETED]:
      data['booking_date'] = datetime.now()
  elif user.role == UserRole.OPERATOR and data['status'] == OrderStatus.IN_PROGRESS:
    data['assignament_date'] = datetime.now()

  return {
    'status': 'ok',
    'order': update(order, data).to_dict()
  }


@order_bp.route('photo/<id>', methods=['GET'])
@error_catching_decorator
def view_order_photo(id: int):
  order: Order = get_by_id(Order, id)
  if not order or not order.photo:
    return {
      'status': 'ko',
      'error': 'Photo not found'
    }, 404

  return send_file(
    io.BytesIO(order.photo),
    mimetype=order.photo_mime_type if order.photo_mime_type else 'application/octet-stream',
    as_attachment=False,
    download_name=f'order_{id}_photo.jpg'
  )


def query_orders(user: ItalcoUser, filters: list, date_filter = {}) -> list[tuple[
  Order, OrderServiceUser, ServiceUser, Service, ItalcoUser, DeliveryGroup, CollectionPoint, Product, Addressee
]]:
  with Session() as session:
    query = session.query(
      Order, OrderServiceUser, ServiceUser, Service, ItalcoUser, DeliveryGroup, CollectionPoint, Product, Addressee
    ).outerjoin(
      DeliveryGroup, Order.delivery_group_id == DeliveryGroup.id
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
      OrderProduct, OrderProduct.order_id == Order.id
    ).outerjoin(
      Product, OrderProduct.product_id == Product.id
    ).outerjoin(
      Addressee, Order.addressee_id == Addressee.id
    )

    if user.role == UserRole.DELIVERY:
      query = query.filter(
        Order.status.in_([OrderStatus.IN_PROGRESS, OrderStatus.DELAY]),
        Order.delivery_group_id == user.delivery_group_id
      )
    elif user.role == UserRole.CUSTOMER:
      query = query.filter(
        ItalcoUser.id == user.id
      )

    dynamic_filters = list(map(
      lambda filter: getattr(globals()[filter['model']], filter['field']) == filter['value'], filters
    ))
    if dynamic_filters:
      query = query.filter(*dynamic_filters)
    if date_filter != {}:
      query = query.filter(
        Order.booking_date >= datetime.strptime(date_filter['start_date'], '%Y-%m-%d'),
        Order.booking_date <= datetime.strptime(date_filter['end_date'], '%Y-%m-%d')
      )

    return query.all()


def query_service_users(service_ids: list[int], user: ItalcoUser) -> list[ServiceUser]:
  with Session() as session:
    user_id = user.id if user.role == UserRole.CUSTOMER else request.json['user_id']
    return session.query(ServiceUser).filter(
      ServiceUser.user_id == user_id,
      ServiceUser.service_id.in_(service_ids)
    ).all()


def format_query_result(tupla: tuple[
  Order, OrderServiceUser, ServiceUser, Service, ItalcoUser, DeliveryGroup, CollectionPoint, Product, Addressee
], list: list[dict], user: ItalcoUser) -> list[dict]:
  for element in list:
    if element['id'] == tupla[0].id:
      element['price'] += tupla[2].price
      add_element_in_list(element, 'services', tupla[3])
      add_element_in_list(element, 'products', tupla[7])
      return list

  output = {
    **tupla[0].to_dict(),
    'price': tupla[2].price,
    'addressee': tupla[8].to_dict(),
    'collection_point': tupla[6].to_dict(),
    'user': tupla[4].format_user(user.role),
    'delivery_group': tupla[5].to_dict() if tupla[5] else None
  }
  add_element_in_list(output, 'services', tupla[3])
  add_element_in_list(output, 'products', tupla[7])
  list.append(output)
  return list


def add_element_in_list(object: dict, key: str, value):
  if not value:
    return object

  if not key in object:
    object[key] = []
  object[key].append(value.to_dict())
  return object

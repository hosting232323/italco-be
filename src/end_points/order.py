import io
import json
from datetime import datetime
from flask import Blueprint, request, send_file

from database_api import Session
from ..database.enum import OrderStatus, UserRole, OrderType
from . import error_catching_decorator, flask_session_authentication
from database_api.operations import create, update, get_by_id, delete, get_by_ids
from ..database.schema import Order, ItalcoUser, Service, ServiceUser, DeliveryGroup, CollectionPoint, \
  OrderServiceUser, Addressee, Photo


order_bp = Blueprint('order_bp', __name__)


# TODO CHECK ELIMINAZIONI RELAZIONI N A N
@order_bp.route('', methods=['POST'])
@error_catching_decorator
@flask_session_authentication([UserRole.CUSTOMER, UserRole.OPERATOR, UserRole.ADMIN])
def create_order(user: ItalcoUser):
  request.json['type'] = OrderType.get_enum_option(request.json['type'])
  service_ids = request.json['service_ids']
  service_users = query_service_users(
    service_ids,
    user.id if user.role == UserRole.CUSTOMER else request.json['user_id']
  )
  del request.json['service_ids']
  if 'user_id' in request.json:
    del request.json['user_id']

  order = create(Order, request.json)
  for service_id in service_ids:
    for service_user in service_users:
      if service_user.service_id == service_id:
        create(OrderServiceUser, {
          'order_id': order.id,
          'service_user_id': service_user.id
        })
        break
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
  elif user.role == UserRole.OPERATOR and data['status'] == OrderStatus.IN_PROGRESS:
    data['assignament_date'] = datetime.now()

  service_ids = data['service_ids']
  service_users = query_service_users(
    service_ids,
    user.id if user.role == UserRole.CUSTOMER else data['user_id']
  )
  order_service_users = query_order_service_users(order)
  del data['service_ids']
  if 'user_id' in data:
    del data['user_id']

  used_index = []
  for service_id in service_ids:
    for service_user in service_users:
      if service_user.service_id == service_id:
        flag = True
        for i, order_service_user in enumerate(order_service_users):
          if order_service_user.service_user_id == service_user.id and not i in used_index:
            used_index.append(i)
            flag = False
            break
        if flag:
          create(OrderServiceUser, {
            'order_id': order.id,
            'service_user_id': service_user.id
          })
        break

  used_index = []
  for order_service_user in order_service_users:
    for i, service_user in enumerate(service_users):
      if order_service_user.service_user_id == service_user.id:
        if service_user.service_id in service_ids and not i in used_index:
          used_index.append(i)
        else:
          delete(order_service_user)
        break

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


@order_bp.route('delivery-group', methods=['PUT'])
@error_catching_decorator
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN])
def assign_delivery_group(user: ItalcoUser):
  orders: list[Order] = get_by_ids(Order, request.json['order_ids'])
  delivery_group: DeliveryGroup = get_by_id(DeliveryGroup, request.json['delivery_group_id'])
  if not delivery_group or not orders:
    return {
      'status': 'ko',
      'error': 'Delivery group o orders non trovati'
    }

  for order in orders:
    update(order, {
      'status': OrderStatus.IN_PROGRESS,
      'delivery_group_id': delivery_group.id
    })
  return {
    'status': 'ok',
    'message': 'Operazione completata con successo'
  }


def query_orders(user: ItalcoUser, filters: list, date_filter = {}) -> list[tuple[
  Order, OrderServiceUser, ServiceUser, Service, ItalcoUser, DeliveryGroup, CollectionPoint, Addressee, Photo
]]:
  with Session() as session:
    query = session.query(
      Order, OrderServiceUser, ServiceUser, Service, ItalcoUser, DeliveryGroup, CollectionPoint, Addressee, Photo
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
      Addressee, Order.addressee_id == Addressee.id
    ).outerjoin(
      Photo, Photo.order_id == Order.id
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


def query_order_service_users(order: Order) -> list[OrderServiceUser]:
  with Session() as session:
    return session.query(OrderServiceUser).filter(
      OrderServiceUser.order_id == order.id
    ).all()


def query_service_users(service_ids: list[int], user_id) -> list[ServiceUser]:
  with Session() as session:
    return session.query(ServiceUser).filter(
      ServiceUser.user_id == user_id,
      ServiceUser.service_id.in_(service_ids)
    ).all()


def format_query_result(tupla: tuple[
  Order, OrderServiceUser, ServiceUser, Service, ItalcoUser, DeliveryGroup, CollectionPoint, Addressee, Photo
], list: list[dict], user: ItalcoUser) -> list[dict]:
  for element in list:
    if element['id'] == tupla[0].id:
      add_photo(element, tupla[8])
      add_service(element, tupla[3], tupla[1], tupla[2].price)
      return list

  output = {
    **tupla[0].to_dict(),
    'price': 0,
    'photos': [],
    'services': [],
    'addressee': tupla[7].to_dict(),
    'collection_point': tupla[6].to_dict(),
    'user': tupla[4].format_user(user.role),
    'delivery_group': tupla[5].to_dict() if tupla[5] else None
  }
  add_photo(output, tupla[8])
  add_service(output, tupla[3], tupla[1], tupla[2].price)
  list.append(output)
  return list


def add_service(object: dict, service: Service, order_service_user: OrderServiceUser, price: float) -> dict:
  if next((s for s in object['services'] if s['order_service_user_id'] == order_service_user.id), None):
    return object

  object['price'] += price
  object['services'].append(service.to_dict())
  object['services'][-1]['order_service_user_id'] = order_service_user.id
  return object


def add_photo(object: dict, photo: Photo) -> dict:
  if photo.id in object['photos']:
    return object

  object['photos'].append(photo.id)
  return object

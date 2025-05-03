from flask import Blueprint, request

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
  service_users = query_service_users(request.json['service_ids'], user)
  products: list[Product] = get_by_ids(Product, request.json['product_ids'])
  if 'user_id' in request.json:
    del request.json['user_id']
  del request.json['service_ids']
  del request.json['product_ids']

  order = create(Order, request.json)
  for service_user in service_users:
    create(OrderServiceUser, {
      'order_id': order.id,
      'service_user_id': service_user.id
    })
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
  for tupla in query_orders(user, request.json['filters']):
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
  request.json['type'] = OrderType.get_enum_option(request.json['type'])
  request.json['status'] = OrderStatus.get_enum_option(request.json['status'])
  return {
    'status': 'ok',
    'order': update(order, request.json).to_dict()
  }


def query_orders(user: ItalcoUser, filters: list) -> list[tuple[
  Order, Service, ItalcoUser, DeliveryGroup, CollectionPoint, Product, Addressee
]]:
  with Session() as session:
    query = session.query(
      Order, Service, ItalcoUser, DeliveryGroup, CollectionPoint, Product, Addressee
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

    if user.role == UserRole.OPERATOR:
      query = query.filter(
        Order.status == OrderStatus.PENDING
      )
    elif user.role == UserRole.DELIVERY:
      query = query.filter(
        Order.status == OrderStatus.IN_PROGRESS,
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
    return query.all()


def query_service_users(service_ids: list[int], user: ItalcoUser) -> list[ServiceUser]:
  with Session() as session:
    user_id = user.id if user.role == UserRole.CUSTOMER else request.json['user_id']
    return session.query(ServiceUser).filter(
      ServiceUser.user_id == user_id,
      ServiceUser.service_id.in_(service_ids)
    ).all()


def format_query_result(
  tupla: tuple[Order, Service, ItalcoUser, DeliveryGroup, CollectionPoint, Product], list: list[dict], user: ItalcoUser
) -> list[dict]:
  for element in list:
    if element['id'] == tupla[0].id:
      add_element_in_list(element, 'services', tupla[1])
      add_element_in_list(element, 'products', tupla[5])
      return list

  output = {
    **tupla[0].to_dict(),
    'addressee': tupla[6].to_dict(),
    'collection_point': tupla[4].to_dict(),
    'user': tupla[2].format_user(user.role),
    'delivery_group': tupla[3].to_dict() if tupla[3] else None
  }
  add_element_in_list(output, 'services', tupla[1])
  add_element_in_list(output, 'products', tupla[5])
  list.append(output)
  return list


def add_element_in_list(object: dict, key: str, value):
  if not value:
    return object

  if not key in object:
    object[key] = []
  object[key].append(value.to_dict())
  return object

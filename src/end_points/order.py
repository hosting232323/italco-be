from flask import Blueprint, request

from database_api import Session
from .service import query_service_user
from ..database.enum import OrderStatus, UserRole
from database_api.operations import create, update, get_by_id
from . import error_catching_decorator, flask_session_authentication
from ..database.schema import Order, ItalcoUser, Service, ServiceUser, DeliveryGroup, CollectionPoint


order_bp = Blueprint('order_bp', __name__)


@order_bp.route('', methods=['POST'])
@error_catching_decorator
@flask_session_authentication([UserRole.CUSTOMER])
def create_order(user: ItalcoUser):
  request.json['service_user_id'] = query_service_user(
    request.json['service_id'], user.id
  ).id
  del request.json['service_id']
  return {
    'status': 'ok',
    'order': create(Order, request.json).to_dict()
  }


@order_bp.route('filter', methods=['POST'])
@error_catching_decorator
@flask_session_authentication([UserRole.OPERATOR, UserRole.DELIVERY, UserRole.ADMIN, UserRole.CUSTOMER])
def filter_orders(user: ItalcoUser):
  return {
    'status': 'ok',
    'orders': [{
      **order[0].to_dict(),
      'service': order[1].to_dict(),
      'collection_point': order[4].to_dict(),
      'user': order[2].format_user(user.role),
      'delivery_group': order[3].to_dict() if order[3] else None
    } for order in query_orders(user, request.json['filters'])]
  }


@order_bp.route('<id>', methods=['PUT'])
@error_catching_decorator
@flask_session_authentication([UserRole.OPERATOR, UserRole.DELIVERY])
def update_order(user: ItalcoUser, id):
  order: Order = get_by_id(Order, int(id))
  request.json['status'] = OrderStatus.get_enum_option(request.json['status'])
  return {
    'status': 'ok',
    'order': update(order, request.json).to_dict()
  }


def query_orders(user: ItalcoUser, filters: list) -> list[tuple[Order, Service, ItalcoUser, DeliveryGroup, CollectionPoint]]:
  with Session() as session:
    query = session.query(
      Order, Service, ItalcoUser, DeliveryGroup, CollectionPoint
    ).outerjoin(
      ServiceUser, Order.service_user_id == ServiceUser.id
    ).outerjoin(
      Service, ServiceUser.service_id == Service.id
    ).outerjoin(
      ItalcoUser, ServiceUser.user_id == ItalcoUser.id
    ).outerjoin(
      DeliveryGroup, Order.delivery_group_id == DeliveryGroup.id
    ).outerjoin(
      CollectionPoint, Order.collection_point_id == CollectionPoint.id
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

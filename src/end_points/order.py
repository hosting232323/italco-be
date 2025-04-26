from flask import Blueprint, request

from database_api import Session
from .service import query_service_user
from ..database.enum import OrderStatus, UserRole
from database_api.operations import create, update, get_by_id
from . import error_catching_decorator, flask_session_authentication
from ..database.schema import Order, ItalcoUser, Service, ServiceUser


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


@order_bp.route('', methods=['GET'])
@error_catching_decorator
def get_orders():
  return {
    'status': 'ok',
    'orders': [{
      **order[0].to_dict(),
      'service': order[1].to_dict(),
      'user': order[2].to_dict()
    } for order in query_orders()]
  }


@order_bp.route('<id>', methods=['PUT'])
@error_catching_decorator
def update_order(id):
  order: Order = get_by_id(Order, int(id))
  request.json['status'] = OrderStatus.get_enum_option(request.json['status'])
  return {
    'status': 'ok',
    'order': update(order, request.json).to_dict()
  }


def query_orders() -> list[Order, Service, ItalcoUser]:
  with Session() as session:
    query = session.query(Order, Service, ItalcoUser).outerjoin(
      ServiceUser, Order.service_user_id == ServiceUser.id
    ).outerjoin(
      Service, ServiceUser.service_id == Service.id
    ).outerjoin(
      ItalcoUser, ServiceUser.user_id == ItalcoUser.id
    )
    if 'status' in request.args:
      query = query.filter(
        Order.status == OrderStatus.get_enum_option(request.args['status'])
      )
    return query.all()

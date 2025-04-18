from flask import Blueprint, request

from database_api import Session
from ..database.schema import Order
from . import error_catching_decorator
from ..database.enum import OrderStatus
from database_api.operations import create, update, get_by_id


order_bp = Blueprint('order_bp', __name__)


@order_bp.route('', methods=['POST'])
@error_catching_decorator
def create_order():
  return {
    'status': 'ok',
    'order': create(Order, request.json).to_dict()
  }


@order_bp.route('', methods=['GET'])
@error_catching_decorator
def get_orders():
  with Session() as session:
    return {
      'status': 'ok',
      'orders': [order.to_dict() for order in query_orders()]
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


def query_orders() -> list[Order]:
  with Session() as session:
    query = session.query(Order)
    if 'status' in request.args:
      query = query.filter(
        Order.status == OrderStatus.get_enum_option(request.args['status'])
      )
    return query.all()

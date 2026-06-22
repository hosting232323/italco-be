from flask import Blueprint, request

from ...database.schema import User
from ...database.enum import UserRole
from ..users.session import flask_session_authentication

from .order import export_order
from .schedule import export_schedule
from .excel import export_orders_excel
from .invoice import export_order_invoice
from .rae import export_rae, export_rae_by_product
from .disposal import export_disposal_attached_a, export_disposal_attached_b, export_disposal_card_index


export_bp = Blueprint('export_bp', __name__)


@export_bp.route('order/<id>', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR, UserRole.CUSTOMER])
def export_order_report(user: User, id):
  return export_order(id, user.id if user.role == UserRole.CUSTOMER else None)


@export_bp.route('invoice', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def export_orders_invoice(_):
  return export_order_invoice(request.json['filters'])


@export_bp.route('schedule/<id>', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
def export_orders_schedule(user: User, id):
  return export_schedule(user, id)


@export_bp.route('rae/<order_id>', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
def export_orders_rae(user: User, order_id):
  return export_rae(user, order_id)


@export_bp.route('rae/product/<rae_product_id>', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
def export_rae_product(user: User, rae_product_id):
  return export_rae_by_product(user, int(rae_product_id))


@export_bp.route('orders/excel', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
def export_selected_orders_excel(_):
  return export_orders_excel(request.json['order_ids'])


@export_bp.route('disposal/<id>/attached-a', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
def export_disposal_attached_a_route(_, id):
  return export_disposal_attached_a(id)


@export_bp.route('disposal/<id>/attached-b', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
def export_disposal_attached_b_route(_, id):
  return export_disposal_attached_b(id)


@export_bp.route('disposal/<id>/card-index', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
def export_disposal_card_index_route(_, id):
  return export_disposal_card_index(id)

from flask import Blueprint, request

from ...database.enum import UserRole
from ...database.schema import User
from ..users.session import flask_session_authentication

from .rae import export_rae
from .order import export_order
from .schedule import export_schedule
from .invoice import export_order_invoice
from .orders_excel import export_orders_excel


export_bp = Blueprint('export_bp', __name__)


@export_bp.route('order/<id>', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR, UserRole.CUSTOMER])
def export_order_report(user: User, id):
  return export_order(user, id)


@export_bp.route('invoice', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def export_orders_invoice(user: User):
  return export_order_invoice(user)


@export_bp.route('schedule/<id>', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
def export_orders_schedule(user: User, id):
  return export_schedule(user, id)


@export_bp.route('rae/<order_id>', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
def export_orders_rae(user: User, order_id):
  return export_rae(user, order_id)


@export_bp.route('orders/excel', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
def export_selected_orders_excel(user: User):
  data = request.json
  order_ids = data.get('order_ids', [])
  return export_orders_excel(user, order_ids)

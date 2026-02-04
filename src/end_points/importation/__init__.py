from flask import Blueprint, request

from ...database.schema import User
from ...database.enum import UserRole
from ..users.session import flask_session_authentication
from api import swagger_decorator, error_catching_decorator

from .pdf import order_import_by_pdf
from .api import save_orders_by_euronics
from .excel import order_import_by_excel, handle_excel_conflict


import_bp = Blueprint('import_bp', __name__)


@import_bp.route('excel', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def excel_order_import(user: User):
  if 'file' not in request.files:
    return {'status': 'ko', 'error': 'Nessun file caricato'}

  return order_import_by_excel(request.files['file'], request.form['customer_id'])


@import_bp.route('excel/conflict', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def handle_conflict(user: User):
  return handle_excel_conflict(request.json['orders'])


@import_bp.route('pdf', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def pdf_order_import(user: User):
  if not request.files:
    return {'status': 'ko', 'error': 'Nessun file caricato'}

  return order_import_by_pdf(request.files, request.form['customer_id'])


@import_bp.route('pdf', methods=['POST'])
@error_catching_decorator
@swagger_decorator
def api_order_import():
  return save_orders_by_euronics()

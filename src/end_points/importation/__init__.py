import json
from flask import Blueprint, request

from ...database.enum import UserRole
from .. import flask_session_authentication
from api import swagger_decorator
from api.storage.files import validate_files, PDF_EXTENSIONS, SPREADSHEET_EXTENSIONS

from .pdf import order_import_by_pdf
from .excel import order_import_by_excel, handle_excel_conflict
from .api import save_orders_by_euronics, update_order_status_by_euronics


import_bp = Blueprint('import_bp', __name__)


def get_customer_id():
  """Il client manda il body in un unico campo 'data' JSON del FormData.
  Il fallback sul campo flat serve ai client non ancora aggiornati."""
  data = request.form.get('data')
  if isinstance(data, str):
    try:
      customer_id = json.loads(data).get('customer_id')
    except json.JSONDecodeError:
      customer_id = None
  else:
    customer_id = request.form.get('customer_id')

  return customer_id or None


@import_bp.route('excel', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def excel_order_import(_):
  if 'file' not in request.files:
    return {'status': 'ko', 'message': 'Nessun file caricato'}

  error = validate_files(request.files.values(), SPREADSHEET_EXTENSIONS)
  if error:
    return {'status': 'ko', 'message': error}

  customer_id = get_customer_id()
  if not customer_id:
    return {'status': 'ko', 'message': 'Punto vendita non specificato'}

  return order_import_by_excel(request.files['file'], customer_id)


@import_bp.route('excel/conflict', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def handle_conflict(_):
  return handle_excel_conflict(request.json['orders'])


@import_bp.route('pdf', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def pdf_order_import(_):
  if not request.files:
    return {'status': 'ko', 'message': 'Nessun file caricato'}

  error = validate_files(request.files.values(), PDF_EXTENSIONS)
  if error:
    return {'status': 'ko', 'message': error}

  customer_id = get_customer_id()
  if not customer_id:
    return {'status': 'ko', 'message': 'Punto vendita non specificato'}

  return order_import_by_pdf(request.files, customer_id)


@import_bp.route('euronics/list', methods=['POST'])
@swagger_decorator
def api_order_import():
  return save_orders_by_euronics()


@import_bp.route('euronics/status', methods=['POST'])
@swagger_decorator
def api_order_status_update():
  return update_order_status_by_euronics(request.json['status'])

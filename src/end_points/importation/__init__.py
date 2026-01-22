from flask import Blueprint, request

from ...database.schema import User
from .pdf import order_import_by_pdf
from ...database.enum import UserRole
from ..users.session import flask_session_authentication
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

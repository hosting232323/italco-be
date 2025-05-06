from io import BytesIO
from xhtml2pdf import pisa
from flask import Blueprint, render_template, make_response, request

from ..database.enum import UserRole
from ..database.schema import ItalcoUser
from .order import query_orders, format_query_result
from . import error_catching_decorator, flask_session_authentication


export_bp = Blueprint('export_bp', __name__)


@export_bp.route('<id>', methods=['GET'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
def export_order_report(user: ItalcoUser, id):
  orders = []
  for tupla in query_orders(user, [{
    'model': 'Order',
    'field': 'id',
    'value': int(id)
  }]):
    orders = format_query_result(tupla, orders, user)
  if len(orders) != 1:
    raise Exception('Numero di ordini trovati non valido')

  result = BytesIO()
  pisa_status = pisa.CreatePDF(src=render_template(
    'order_report.html',
    id=orders[0]['id'],
    dpc=orders[0]['dpc'],
    drc=orders[0]['drc'],
    customer=orders[0]['user'],
    addressee=orders[0]['addressee'],
    collection_point=orders[0]['collection_point'],
    note=orders[0]['customer_note'] if 'customer_note' in orders[0] else '/',
    services=', '.join([service['name'] for service in orders[0]['services']]),
    products=', '.join([product['name'] for product in orders[0]['products']])
  ), dest=result)
  if pisa_status.err:
    raise Exception('Errore nella creazione del PDF')

  response = make_response(result.getvalue())
  response.headers['Content-Type'] = 'application/pdf'
  response.headers['Content-Disposition'] = 'inline; filename=report.pdf'
  return response


@export_bp.route('invoice', methods=['POST'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN])
def export_orders_invoice(user: ItalcoUser):
  orders = []
  for tupla in query_orders(user, request.json['filters'], request.json['date_filter']):
    orders = format_query_result(tupla, orders, user)
  if len(orders) == 0:
    raise Exception('Numero di ordini trovati non valido')

  result = BytesIO()
  pisa_status = pisa.CreatePDF(src=render_template(
    'orders_invoice.html',
    orders=orders,
    total=sum([order['price'] for order in orders]),
    end_date=request.json['date_filter']['end_date'],
    start_date=request.json['date_filter']['start_date'],
    customer=next((f['value'] for f in request.json['filters']
      if f['model'] == 'ItalcoUser' and f['field'] == 'email'), None)
  ), dest=result)
  if pisa_status.err:
    raise Exception('Errore nella creazione del PDF')

  response = make_response(result.getvalue())
  response.headers['Content-Type'] = 'application/pdf'
  response.headers['Content-Disposition'] = 'inline; filename=report.pdf'
  return response
  
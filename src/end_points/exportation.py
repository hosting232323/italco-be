import base64
from io import BytesIO
from xhtml2pdf import pisa
from flask import Blueprint, render_template, make_response, request

from database_api.operations import get_by_id
from .users.queries import format_user_with_info
from ..database.enum import UserRole, OrderStatus
from ..database.schema import User, Order, RaeProduct
from .users.session import flask_session_authentication
from .orders.queries import query_orders, format_query_result as format_order_query_result
from .schedule.queries import query_schedules, format_query_result as format_schedule_query_result


export_bp = Blueprint('export_bp', __name__)


@export_bp.route('order/<id>', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR, UserRole.CUSTOMER])
def export_order_report(user: User, id):
  orders = []
  for tupla in query_orders(user, [{'model': 'Order', 'field': 'id', 'value': int(id)}]):
    orders = format_order_query_result(tupla, orders, user)
  if len(orders) != 1:
    raise Exception('Numero di ordini trovati non valido')

  result = BytesIO()
  pisa_status = pisa.CreatePDF(
    src=render_template(
      'order_report.html',
      id=orders[0]['id'],
      dpc=orders[0]['dpc'],
      drc=orders[0]['drc'],
      booking_date=orders[0].get('booking_date', '/'),
      customer=orders[0]['user'],
      address=orders[0]['address'],
      addressee=orders[0]['addressee'],
      addressee_contact=orders[0].get('addressee_contact', '/'),
      products=orders[0]['products'],
      note=orders[0].get('customer_note', '/'),
      signature=get_signature(get_by_id(Order, orders[0]['id'])),
    ),
    dest=result,
  )
  if pisa_status.err:
    raise Exception('Errore nella creazione del PDF')

  return export_pdf(result.getvalue())


@export_bp.route('invoice', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def export_orders_invoice(user: User):
  orders = []
  for tupla in query_orders(
    user,
    request.json['filters'] + [{'model': 'Order', 'field': 'status', 'value': OrderStatus.COMPLETED}],
  ):
    orders = format_order_query_result(tupla, orders, user)
  if len(orders) == 0:
    raise Exception('Numero di ordini trovati non valido')

  for filter in request.json['filters']:
    if filter['field'] == 'booking_date' and filter['model'] == 'Order':
      start_date = filter['value'][0]
      end_date = filter['value'][1]
      break

  result = BytesIO()
  pisa_status = pisa.CreatePDF(
    src=render_template(
      'orders_invoice.html',
      orders=orders,
      end_date=start_date,
      start_date=end_date,
      total=sum([order['price'] for order in orders]),
      customer=orders[0]['user']['nickname'] if orders else None,
    ),
    dest=result,
  )
  if pisa_status.err:
    raise Exception('Errore nella creazione del PDF')

  return export_pdf(result.getvalue())


@export_bp.route('schedule/<id>', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
def export_orders_schedule(user: User, id):
  schedules = []
  for tupla in query_schedules([{'model': 'Schedule', 'field': 'id', 'value': int(id)}]):
    schedules = format_schedule_query_result(tupla, schedules, user)
  if len(schedules) != 1:
    raise Exception('Numero di schedule trovati non valido')

  orders = []
  for tupla in query_orders(
    user,
    [
      {
        'model': 'Order',
        'field': 'id',
        'value': [order['order_id'] for order in schedules[0]['schedule_items'] if order['operation_type'] == 'Order'],
      }
    ],
  ):
    orders = format_order_query_result(tupla, orders, user)

  result = BytesIO()
  pisa_status = pisa.CreatePDF(
    src=render_template(
      'schedules_report.html',
      id=schedules[0]['id'],
      date=schedules[0]['date'],
      users=', '.join([user['nickname'] for user in schedules[0]['users']]),
      transport=schedules[0]['transport']['name'],
      orders=[{**order, 'signature': get_signature(get_by_id(Order, order['id']))} for order in orders],
    ),
    dest=result,
  )
  if pisa_status.err:
    raise Exception('Errore nella creazione del PDF')

  return export_pdf(result.getvalue())


@export_bp.route('rae/<order_id>', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
def export_rae(user: User, order_id):
  orders = []
  for tupla in query_orders(user, [{'model': 'Order', 'field': 'id', 'value': int(order_id)}]):
    orders = format_order_query_result(tupla, orders, user)
  if len(orders) != 1:
    raise Exception('Numero di ordini trovati non valido')

  rae_product = None
  for product_data in orders[0]['products'].values():
    if product_data['rae_product_id']:
      rae_product = get_by_id(RaeProduct, product_data['rae_product_id'])
  if not rae_product:
    raise Exception('Prodotto rae non identificato')

  result = BytesIO()
  pisa_status = pisa.CreatePDF(
    src=render_template(
      'rae_product.html',
      rae_product=rae_product,
      address=orders[0]['address'],
      addressee=orders[0]['addressee'],
      customer=format_user_with_info(get_by_id(User, orders[0]['user']['id']), user.role),
    ),
    dest=result,
  )
  if pisa_status.err:
    raise Exception('Errore nella creazione del PDF')

  return export_pdf(result.getvalue())


def get_signature(order: Order):
  if order.signature:
    signature_base64 = base64.b64encode(order.signature).decode('utf-8')
    return f'data:image/png;base64,{signature_base64}'
  else:
    return None


def export_pdf(document):
  response = make_response(document)
  response.headers['Content-Type'] = 'application/pdf'
  response.headers['Content-Disposition'] = 'inline; filename=report.pdf'
  return response

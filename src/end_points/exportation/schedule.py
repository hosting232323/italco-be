from io import BytesIO
from xhtml2pdf import pisa
from flask import render_template

from .rae import get_rae_products_by_order
from ...database.schema import User, Order
from .utils import get_signature, export_pdf
from database_api.operations import get_by_id
from ..users.queries import format_user_with_info
from ..orders.queries import query_orders, format_query_result as format_order_query_result
from ..schedule.queries import query_schedules, format_query_result as format_schedule_query_result


def export_schedule(user: User, id):
  schedules = []
  for tupla in query_schedules([{'model': 'Schedule', 'field': 'id', 'value': int(id)}]):
    schedules = format_schedule_query_result(tupla, schedules, user)
  if len(schedules) != 1:
    return {'status': 'ko', 'error': 'Numero di borderò trovati non valido'}

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
  for order in orders:
    order['rae_products'] = get_rae_products_by_order(order)
    order['customer'] = format_user_with_info(get_by_id(User, order['user']['id']), user.role)

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
    return {'status': 'ko', 'error': 'Errore nella creazione del PDF'}

  return export_pdf(result.getvalue())

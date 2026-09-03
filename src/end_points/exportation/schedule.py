from io import BytesIO
from xhtml2pdf import pisa
from flask import render_template

from ...database.schema import User, Order
from .utils import get_signature_slots, export_pdf, company_context
from .rae import get_rae_export_info_by_order
from database_api.operations import get_by_id
from ..users.queries import format_user_with_info
from ..orders.queries import query_orders, format_query_result as format_order_query_result
from ..schedule.queries import query_schedules, format_query_result as format_schedule_query_result


# Massimo ordini per pagina della tabella "Ordini": se il contenuto di un
# gruppo non ci sta fisicamente su una pagina, xhtml2pdf continua da sola
# sulla successiva (ripetendo l'intestazione, vedi repeat="1" nel template).
ORDERS_PER_TABLE_PAGE = 5


def _paginate(items: list, page_size: int) -> list[list]:
  return [items[index : index + page_size] for index in range(0, len(items), page_size)]


def export_schedule(user: User, id):
  schedules = []
  for tupla in query_schedules([{'model': 'Schedule', 'field': 'id', 'value': int(id)}]):
    schedules = format_schedule_query_result(tupla, schedules)
  if len(schedules) != 1:
    return {'status': 'ko', 'message': 'Numero di borderò trovati non valido'}

  orders = []
  for tupla in query_orders(
    [
      {
        'field': 'id',
        'model': 'Order',
        'value': [order['order_id'] for order in schedules[0]['schedule_items'] if order['operation_type'] == 'Order'],
      }
    ],
  ):
    orders = format_order_query_result(tupla, orders)
  for order in orders:
    order['rae_products'] = get_rae_export_info_by_order(order)
    order['customer'] = format_user_with_info(get_by_id(User, order['user']['id']), user.role)
    delivery_signature, anomaly_signature = get_signature_slots(get_by_id(Order, order['id']))
    order['delivery_signature'] = delivery_signature
    order['anomaly_signature'] = anomaly_signature

  result = BytesIO()
  pisa_status = pisa.CreatePDF(
    src=render_template(
      'schedules_report.html',
      id=schedules[0]['id'],
      date=schedules[0]['date'],
      transport=schedules[0]['transport']['name'],
      users=', '.join([user['nickname'] for user in schedules[0]['users']]),
      orders=orders,
      order_pages=_paginate(orders, ORDERS_PER_TABLE_PAGE),
      **company_context(),
    ),
    dest=result,
  )
  if pisa_status.err:
    return {'status': 'ko', 'message': 'Errore nella creazione del PDF'}

  return export_pdf(result.getvalue())

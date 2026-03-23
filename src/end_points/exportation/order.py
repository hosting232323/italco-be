from io import BytesIO
from xhtml2pdf import pisa
from flask import render_template

from ...database.schema import User, Order
from .utils import get_signature, export_pdf
from database_api.operations import get_by_id
from ..orders.queries import query_orders, format_query_result


def export_order(user: User, id):
  orders = []
  for tupla in query_orders(user, [{'model': 'Order', 'field': 'id', 'value': int(id)}]):
    orders = format_query_result(tupla, orders, user)
  if len(orders) != 1:
    return {'status': 'ko', 'error': 'Numero di ordini trovati non valido'}
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
    return {'status': 'ko', 'error': 'Errore nella creazione del PDF'}

  return export_pdf(result.getvalue())

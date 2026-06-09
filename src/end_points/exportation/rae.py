from io import BytesIO
from xhtml2pdf import pisa
from flask import render_template

from .utils import export_pdf
from ...database.schema import User
from database_api.operations import get_by_id
from ..rae.queries import get_product_and_group
from ..users.queries import format_user_with_info
from ..schedule.queries import get_schedule_by_order
from ..orders.queries import query_orders, format_query_result


def export_rae(user: User, order_id):
  orders = []
  for tupla in query_orders([{'model': 'Order', 'field': 'id', 'value': int(order_id)}]):
    orders = format_query_result(tupla, orders)
  if len(orders) != 1:
    return {'status': 'ko', 'error': 'Numero di ordini trovati non valido'}

  rae_products = get_rae_export_info_by_order(orders[0])
  if len(rae_products) == 0:
    return {'status': 'ko', 'error': 'Nessun prodotto rae identificato'}

  result = BytesIO()
  pisa_status = pisa.CreatePDF(
    src=render_template(
      'rae_product.html',
      rae_products=rae_products,
      address=orders[0]['address'],
      addressee=orders[0]['addressee'],
      created_at=orders[0]['created_at'],
      customer=format_user_with_info(get_by_id(User, orders[0]['user']['id']), user.role),
    ),
    dest=result,
  )
  if pisa_status.err:
    return {'status': 'ko', 'error': 'Errore nella creazione del PDF'}

  return export_pdf(result.getvalue())


def get_rae_export_info_by_order(order: dict) -> list[dict]:
  rae_products = []
  for product_data in order['products'].values():
    if 'rae_product' in product_data and product_data['rae_product']:
      schedule_date = get_schedule_by_order(order['id']).date
      rae_products.append(
        {
          'date': schedule_date.strftime('%d/%m/%Y'),
          'data': get_product_and_group(product_data['rae_product']['id']),
        }
      )
  return rae_products

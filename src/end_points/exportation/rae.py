from io import BytesIO
from xhtml2pdf import pisa
from flask import render_template

from .utils import export_pdf
from database_api.operations import get_by_id
from ...database.schema import User, RaeProduct
from ..users.queries import format_user_with_info
from ..rae_product import query_count_rae_products
from ..schedule.queries import get_schedule_by_order
from ..orders.queries import query_orders, format_query_result


def export_rae(user: User, order_id):
  orders = []
  for tupla in query_orders(user, [{'model': 'Order', 'field': 'id', 'value': int(order_id)}]):
    orders = format_query_result(tupla, orders, user)
  if len(orders) != 1:
    return {'status': 'ko', 'error': 'Numero di ordini trovati non valido'}

  rae_products = get_rae_products_by_order(orders[0])
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


def get_rae_products_by_order(order: dict) -> list[dict]:
  rae_products = []
  for product_data in order['products'].values():
    if 'rae_product_id' in product_data and product_data['rae_product_id']:
      schedule = get_schedule_by_order(order['id'])
      rae_products.append(
        {
          'quantity': product_data['rae_product_quantity'],
          'data': get_by_id(RaeProduct, product_data['rae_product_id']),
          'date': schedule.date.strftime('%d/%m/%Y') if schedule else 'N/D',
          'index': query_count_rae_products(product_data['services'][0]['product_id'], order['user']['id']),
        }
      )
  return rae_products

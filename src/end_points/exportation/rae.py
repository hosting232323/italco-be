from io import BytesIO
from xhtml2pdf import pisa
from flask import render_template

from .utils import export_pdf
from ...database.enum import RaeStatus
from database_api.operations import get_by_id
from ..rae.queries import get_product_and_group
from ..users.queries import format_user_with_info
from ...database.schema import User, RaeProduct, Order
from ..orders.queries import query_orders, format_query_result


def export_rae(user: User, order_id):
  order = _get_order_dict(int(order_id))
  if not order:
    return {'status': 'ko', 'error': 'Numero di ordini trovati non valido'}

  rae_products = get_rae_export_info_by_order(order)
  if len(rae_products) == 0:
    return {'status': 'ko', 'error': 'Nessun prodotto rae identificato'}

  return _render_rae_pdf(rae_products, order, get_by_id(User, order['user']['id']), user.role)


def export_rae_by_product(user: User, rae_product_id: int):
  rae_product: RaeProduct = get_by_id(RaeProduct, rae_product_id)
  if not rae_product:
    return {'status': 'ko', 'error': 'Prodotto rae non trovato'}

  order: Order = get_by_id(Order, rae_product.order_id)
  if not order:
    return {'status': 'ko', 'error': 'Ordine non trovato'}

  if rae_product.status == RaeStatus.GENERATED:
    return {'status': 'ko', 'error': 'Prodotto rae non ancora emesso'}

  order_dict = _get_order_dict(order.id)
  if not order_dict:
    return {'status': 'ko', 'error': 'Errore nel recupero dati ordine'}

  return _render_rae_pdf(
    [get_product_and_group(rae_product.id)],
    order_dict,
    get_by_id(User, rae_product.user_id),
    user.role,
  )


def get_rae_export_info_by_order(order: dict) -> list[dict]:
  return [
    product_data['rae_product']
    for product_data in order['products'].values()
    if product_data.get('rae_product') and product_data['rae_product'].get('dtr_date')
  ]


def _get_order_dict(order_id: int) -> dict | None:
  orders = []
  for tupla in query_orders([{'model': 'Order', 'field': 'id', 'value': order_id}]):
    orders = format_query_result(tupla, orders)

  return orders[0] if len(orders) == 1 else None


def _render_rae_pdf(rae_products: list[dict], order: dict, customer: User, role) -> dict:
  result = BytesIO()
  pisa_status = pisa.CreatePDF(
    src=render_template(
      'rae_product.html',
      rae_products=rae_products,
      address=order['address'],
      addressee=order['addressee'],
      created_at=order['created_at'],
      customer=format_user_with_info(customer, role),
    ),
    dest=result,
  )
  if pisa_status.err:
    return {'status': 'ko', 'error': 'Errore nella creazione del PDF'}

  return export_pdf(result.getvalue())

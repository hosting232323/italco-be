from io import BytesIO
from xhtml2pdf import pisa
from flask import render_template

from .utils import export_pdf
from ...database.enum import RaeStatus, UserRole
from database_api.operations import get_by_id
from ..rae.queries import get_product_and_group, query_rae_products
from ..users.queries import format_user_with_info
from ...database.schema import User, RaeProduct, Order
from ..orders.queries import query_orders, format_query_result


MAX_ADDRESSEE_WORD = 16

RAE_STATUS_LABELS = {
  RaeStatus.GENERATED: 'Generato',
  RaeStatus.EMITTED: 'Emesso',
  RaeStatus.LDR: 'LDR',
  RaeStatus.DISPOSED_OFF: 'Smaltito',
  RaeStatus.ANNULLED: 'Annullato',
}


def export_rae(user: User, order_id):
  order = _get_order_dict(int(order_id))
  if not order:
    return {'status': 'ko', 'message': 'Numero di ordini trovati non valido'}

  rae_products = get_rae_export_info_by_order(order)
  if len(rae_products) == 0:
    return {'status': 'ko', 'message': 'Nessun prodotto rae identificato'}

  return _render_rae_pdf(rae_products, order, get_by_id(User, order['user']['id']), user.role)


def export_rae_by_product(user: User, rae_product_id: int):
  rae_product: RaeProduct = get_by_id(RaeProduct, rae_product_id)
  if not rae_product:
    return {'status': 'ko', 'message': 'Prodotto rae non trovato'}

  order: Order = get_by_id(Order, rae_product.order_id)
  if not order:
    return {'status': 'ko', 'message': 'Ordine non trovato'}

  if rae_product.status == RaeStatus.GENERATED:
    return {'status': 'ko', 'message': 'Prodotto rae non ancora emesso'}

  order_dict = _get_order_dict(order.id)
  if not order_dict:
    return {'status': 'ko', 'message': 'Errore nel recupero dati ordine'}

  return _render_rae_pdf(
    [get_product_and_group(rae_product.id)],
    order_dict,
    get_by_id(User, rae_product.user_id),
    user.role,
  )


def export_rae_card_index(user: User, user_id: int, year: int):
  customer: User = get_by_id(User, user_id)
  if not customer or customer.role != UserRole.CUSTOMER:
    return {'status': 'ko', 'message': 'Punto vendita non trovato'}

  filters = [
    {'model': 'RaeProduct', 'field': 'user_id', 'value': user_id},
    {'model': 'RaeProduct', 'field': 'dtr_date', 'value': [f'{year}-01-01', f'{year}-12-31']},
  ]
  rae_products = {}
  for rae_product, group, _, order, _, _ in query_rae_products(filters):
    rae_products.setdefault(rae_product.id, (rae_product, group, order))

  if not rae_products:
    return {'status': 'ko', 'message': 'Nessun ritiro RAEE trovato per questo punto vendita in questo anno'}

  rows = [
    {
      'dtr': rae_product.dtr_date.strftime('%d/%m/%Y'),
      'n_ddt': rae_product.number,
      'nome_prodotto': group.name,
      'codice_cer': group.cer_code,
      'raggruppamento': group.group_code,
      'quantita': rae_product.quantity or 0,
      'destinatario': order.addressee,
      'destinatario_lungo': _has_long_word(order.addressee),
      'stato': RAE_STATUS_LABELS.get(rae_product.status, ''),
    }
    for rae_product, group, order in sorted(rae_products.values(), key=lambda t: (t[0].dtr_date, t[0].id))
  ]
  total = sum(row['quantita'] for row in rows)

  result = BytesIO()
  pisa_status = pisa.CreatePDF(
    src=render_template(
      'rae_card_index.html',
      customer=format_user_with_info(customer, user.role),
      year=year,
      rows=rows,
      total=total,
    ),
    dest=result,
  )
  if pisa_status.err:
    return {'status': 'ko', 'message': 'Errore nella creazione del PDF'}
  return export_pdf(result.getvalue())


def _has_long_word(text: str | None) -> bool:
  """Vero se una singola parola non entra nella colonna Destinatario.

  Solo per queste righe lo schedario spezza a caratteri: sulle altre il
  taglio a fine parola resta piu' leggibile.
  """
  return max((len(word) for word in (text or '').split()), default=0) > MAX_ADDRESSEE_WORD


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
    return {'status': 'ko', 'message': 'Errore nella creazione del PDF'}

  return export_pdf(result.getvalue())

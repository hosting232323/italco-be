from io import BytesIO
from collections import defaultdict
from xhtml2pdf import pisa
from flask import render_template
from .utils import export_pdf
from ..rae.disposal import format_query_result, query_rae_disposals
from ..rae.queries import get_disposal_for_export, get_disposal_rae_products
from ..schedule.queries import get_schedule_by_order


def format_row(rae_product, rae_product_group, user, order) -> dict:
  schedule = get_schedule_by_order(order.id)
  return {
    'dtr': schedule.date.strftime('%d/%m/%Y') if schedule and schedule.date else '/',
    'n_ddt': rae_product.number,
    'nome_prodotto': rae_product_group.name,
    'codice_cer': rae_product_group.cer_code,
    'raggruppamento': rae_product_group.group_code,
    'quantita': rae_product.quantity or 0,
    'cliente': user.nickname,
    'destinatario': order.addressee,
  }


def export_disposal_attached_a(disposal_id: int):
  disposal = get_disposal_for_export(int(disposal_id))
  if not disposal:
    return {'status': 'ko', 'message': 'Smaltimento non trovato'}

  rae_products = get_disposal_rae_products(int(disposal_id))
  if not rae_products:
    return {'status': 'ko', 'message': 'Nessun prodotto RAE associato a questo smaltimento'}

  rows = sorted([format_row(rp, rpg, u, o) for rp, rpg, u, o in rae_products], key=lambda r: r['dtr'])
  codice_afir = f'{rae_products[0][2].id}-AFIR-{disposal_id}'
  total = sum(r['quantita'] for r in rows)

  result = BytesIO()
  pisa_status = pisa.CreatePDF(
    src=render_template('disposal_attached_a.html', disposal=disposal, rows=rows, codice_afir=codice_afir, total=total),
    dest=result,
  )
  if pisa_status.err:
    return {'status': 'ko', 'message': 'Errore nella creazione del PDF'}
  return export_pdf(result.getvalue())


def export_disposal_attached_b(disposal_id: int):
  disposals = []
  for row in query_rae_disposals(int(disposal_id)):
    disposals = format_query_result(row, disposals)
  if len(disposals) != 1:
    return {'status': 'ko', 'message': 'Numero di smaltimenti trovati non valido'}

  if not disposals[0]['group_quantities']:
    return {'status': 'ko', 'message': 'Nessun prodotto RAE associato a questo smaltimento'}

  rows = [
    {'raggruppamento': group_code, 'quantita': qty}
    for group_code, qty in sorted(disposals[0]['group_quantities'].items())
  ]
  total = sum(r['quantita'] for r in rows)

  result = BytesIO()
  pisa_status = pisa.CreatePDF(
    src=render_template('disposal_attached_b.html', disposal=disposals[0], rows=rows, total=total),
    dest=result,
  )
  if pisa_status.err:
    return {'status': 'ko', 'message': 'Errore nella creazione del PDF'}
  return export_pdf(result.getvalue())


def export_disposal_card_index(disposal_id: int):
  disposal = get_disposal_for_export(int(disposal_id))
  if not disposal:
    return {'status': 'ko', 'message': 'Smaltimento non trovato'}

  by_customer: dict[str, list[dict]] = defaultdict(list)
  for rp, rpg, u, o in get_disposal_rae_products(int(disposal_id)):
    by_customer[u.nickname].append(format_row(rp, rpg, u, o))

  if not by_customer:
    return {'status': 'ko', 'message': 'Nessun prodotto RAE associato a questo smaltimento'}

  customers = [
    {
      'nome': nome,
      'rae_products': sorted(items, key=lambda r: r['dtr']),
      'subtotale': sum(r['quantita'] for r in items),
    }
    for nome, items in sorted(by_customer.items())
  ]
  total = sum(c['subtotale'] for c in customers)

  result = BytesIO()
  pisa_status = pisa.CreatePDF(
    src=render_template('disposal_card_index.html', disposal=disposal, customers=customers, total=total),
    dest=result,
  )
  if pisa_status.err:
    return {'status': 'ko', 'message': 'Errore nella creazione del PDF'}
  return export_pdf(result.getvalue())

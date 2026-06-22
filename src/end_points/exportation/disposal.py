from io import BytesIO
from collections import defaultdict
from xhtml2pdf import pisa
from flask import render_template

from .utils import export_pdf
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


def export_disposal_pickup_list(disposal_id: int):
  disposal = get_disposal_for_export(int(disposal_id))
  if not disposal:
    return {'status': 'ko', 'error': 'Smaltimento non trovato'}

  rows = sorted(
    [format_row(rp, rpg, u, o) for rp, rpg, u, o in get_disposal_rae_products(int(disposal_id))],
    key=lambda r: r['dtr'],
  )
  if not rows:
    return {'status': 'ko', 'error': 'Nessun prodotto RAE associato a questo smaltimento'}

  total = sum(r['quantita'] for r in rows)

  result = BytesIO()
  pisa_status = pisa.CreatePDF(
    src=render_template('disposal_pickup_list.html', disposal=disposal, rows=rows, total=total),
    dest=result,
  )
  if pisa_status.err:
    return {'status': 'ko', 'error': 'Errore nella creazione del PDF'}
  return export_pdf(result.getvalue())


def export_disposal_group_summary(disposal_id: int):
  disposal = get_disposal_for_export(int(disposal_id))
  if not disposal:
    return {'status': 'ko', 'error': 'Smaltimento non trovato'}

  groups: dict[str, int] = defaultdict(int)
  for rp, rpg, _u, _o in get_disposal_rae_products(int(disposal_id)):
    groups[rpg.group_code] += rp.quantity or 0

  if not groups:
    return {'status': 'ko', 'error': 'Nessun prodotto RAE associato a questo smaltimento'}

  rows = [{'raggruppamento': group_code, 'quantita': qty} for group_code, qty in sorted(groups.items())]
  total = sum(r['quantita'] for r in rows)

  result = BytesIO()
  pisa_status = pisa.CreatePDF(
    src=render_template('disposal_group_summary.html', disposal=disposal, rows=rows, total=total),
    dest=result,
  )
  if pisa_status.err:
    return {'status': 'ko', 'error': 'Errore nella creazione del PDF'}
  return export_pdf(result.getvalue())


def export_disposal_by_sale_point(disposal_id: int):
  disposal = get_disposal_for_export(int(disposal_id))
  if not disposal:
    return {'status': 'ko', 'error': 'Smaltimento non trovato'}

  by_customer: dict[str, list[dict]] = defaultdict(list)
  for rp, rpg, u, o in get_disposal_rae_products(int(disposal_id)):
    by_customer[u.nickname].append(format_row(rp, rpg, u, o))

  if not by_customer:
    return {'status': 'ko', 'error': 'Nessun prodotto RAE associato a questo smaltimento'}

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
    src=render_template('disposal_by_sale_point.html', disposal=disposal, customers=customers, total=total),
    dest=result,
  )
  if pisa_status.err:
    return {'status': 'ko', 'error': 'Errore nella creazione del PDF'}
  return export_pdf(result.getvalue())

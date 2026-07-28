from io import BytesIO
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

  grouped = {}
  for rp, rpg, u, o in rae_products:
    grouped.setdefault(u.id, {'user': u, 'rows': []})['rows'].append(format_row(rp, rpg, u, o))

  sections = []
  for group in sorted(grouped.values(), key=lambda g: g['user'].nickname):
    user = group['user']
    rows = sorted(group['rows'], key=lambda r: r['dtr'])
    sections.append(
      {
        'punto_vendita': user.nickname,
        'codice_afir': f'{user.id}-AFIR-{disposal_id}',
        'rows': rows,
        'total': sum(r['quantita'] for r in rows),
      }
    )

  result = BytesIO()
  pisa_status = pisa.CreatePDF(
    src=render_template('disposal_attached_a.html', disposal=disposal, sections=sections),
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

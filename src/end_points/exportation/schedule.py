from io import BytesIO
from pypdf import PdfReader
from xhtml2pdf import pisa
from flask import render_template

from ...database.schema import User, Order, RaeDisposalPlace
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

# Corpi candidati per la tabella "Ordini", dal più grande al più piccolo.
# L'ultimo è il corpo storico: è il minimo sotto cui non si scende, e quello
# che il CSS usa come default se nessuno passa la variabile.
ORDERS_FONT_SIZES = (16, 15, 14, 13, 12, 11, 10)

# Pagine orizzontali che si accetta di spendere in più rispetto al minimo pur
# di stampare più grande. A zero un corpo più grande non costa mai carta, ed è
# il motivo del default: su un borderò che sta in una pagina sola, concederne
# anche una soltanto vuol dire raddoppiarlo per guadagnare un corpo.
ORDERS_EXTRA_PAGES_BUDGET = 0


def _paginate(items: list, page_size: int) -> list[list]:
  return [items[index : index + page_size] for index in range(0, len(items), page_size)]


def _landscape_pages(pdf: bytes) -> int:
  """Quante pagine orizzontali ha il PDF, cioè quelle della sezione Ordini."""
  return sum(1 for page in PdfReader(BytesIO(pdf)).pages if page.mediabox.width > page.mediabox.height)


def _render_orders_probe(order_pages: list[list], company: dict, font_size: int) -> bytes:
  result = BytesIO()
  pisa.CreatePDF(
    src=render_template(
      'schedule_orders_probe.html', order_pages=order_pages, schedule_orders_font_size=font_size, **company
    ),
    dest=result,
  )
  return result.getvalue()


def _fit_orders_font_size(order_pages: list[list], company: dict) -> int:
  """Il corpo più grande per la tabella "Ordini" che non costa pagine.

  L'altezza di una riga la decide solo l'impaginazione: le celle tengono un
  numero variabile di prodotti e servizi, e xhtml2pdf manda l'intera riga alla
  pagina dopo appena non ci sta. Stimarla a mano vorrebbe dire riscrivere il
  calcolo di reportlab, quindi si stampa davvero la sola sezione Ordini a ogni
  corpo candidato e si contano le pagine. Il render di prova è leggero perché
  lascia fuori schede ordine e formulari RAE, ma tiene carta intestata e
  firma del trasportatore, che sulla pagina orizzontale occupano altezza.
  """
  if not order_pages:
    return ORDERS_FONT_SIZES[0]

  measured = {}

  def pages(index: int) -> int:
    if index not in measured:
      measured[index] = _landscape_pages(_render_orders_probe(order_pages, company, ORDERS_FONT_SIZES[index]))
    return measured[index]

  last = len(ORDERS_FONT_SIZES) - 1
  # Una pagina orizzontale per gruppo è il minimo possibile: se già il corpo
  # più grande ci riesce non c'è niente da guadagnare a rimpicciolire.
  if pages(0) == len(order_pages):
    return ORDERS_FONT_SIZES[0]

  budget = pages(last) + ORDERS_EXTRA_PAGES_BUDGET

  # Rimpicciolire il testo non può far crescere le pagine, quindi la scala è
  # monotona e si biseca: si cerca il primo corpo che rientra nel budget, che
  # essendo la scala ordinata dal più grande è anche il più grande. L'ultimo
  # ci rientra per costruzione, così la ricerca finisce sempre su un valore
  # valido e i corpi in mezzo non si stampano nemmeno.
  low, high = 0, last
  while low < high:
    middle = (low + high) // 2
    if pages(middle) <= budget:
      high = middle
    else:
      low = middle + 1

  return ORDERS_FONT_SIZES[low]


def export_schedule(user: User, id):
  schedules = []
  for tupla in query_schedules([{'model': 'Schedule', 'field': 'id', 'value': int(id)}]):
    schedules = format_schedule_query_result(tupla, schedules)
  if len(schedules) != 1:
    return {'status': 'ko', 'message': 'Numero di borderò trovati non valido'}

  # Il luogo di smaltimento è quello scelto una volta sola sul borderò (non
  # quello del Disposal, che a questo punto non esiste ancora: lo smaltimento
  # vero e proprio è un passo successivo e separato): lo stesso valore per
  # tutti i prodotti RAE che il borderò raccoglie.
  disposal_place_id = schedules[0].get('rae_disposal_place_id')
  disposal_place = get_by_id(RaeDisposalPlace, disposal_place_id).to_dict() if disposal_place_id else None

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
    for rae_product in order['rae_products']:
      rae_product['disposal_place'] = disposal_place
    order['customer'] = format_user_with_info(get_by_id(User, order['user']['id']), user.role)
    delivery_signature, anomaly_signature = get_signature_slots(get_by_id(Order, order['id']))
    order['delivery_signature'] = delivery_signature
    order['anomaly_signature'] = anomaly_signature

  company = company_context()
  order_pages = _paginate(orders, ORDERS_PER_TABLE_PAGE)

  result = BytesIO()
  pisa_status = pisa.CreatePDF(
    src=render_template(
      'schedules_report.html',
      id=schedules[0]['id'],
      date=schedules[0]['date'],
      transport=schedules[0]['transport']['name'],
      users=', '.join([user['nickname'] for user in schedules[0]['users']]),
      orders=orders,
      order_pages=order_pages,
      schedule_orders_font_size=_fit_orders_font_size(order_pages, company),
      **company,
    ),
    dest=result,
  )
  if pisa_status.err:
    return {'status': 'ko', 'message': 'Errore nella creazione del PDF'}

  return export_pdf(result.getvalue())

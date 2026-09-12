import os
import base64
import mimetypes
from functools import lru_cache
from html import escape as xml_escape
from flask import make_response
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph

from api.storage import get_full_path

from ... import STATIC_FOLDER
from ...database.schema import Order, Company
from ...database.enum import OrderStatus
from ...database.queries import get_active_company


LOGO_SUBFOLDER = 'company-logos'

# Logo Ares usato quando l'attività non ne ha caricato uno proprio. Sta accanto
# a questo modulo così il path non dipende dalla working directory, come la
# targhetta "Powered by" della carta intestata.
ARES_LOGO_PATH = os.path.join(os.path.dirname(__file__), 'ares_logo.png')
POWERED_TAG_PATH = os.path.join(os.path.dirname(__file__), 'powered_tag.svg')

# Trascrizione in pt delle regole di templates/components/base.html (classi
# .letterhead*), usata solo per prevedere quanto sarà alto il blocco dati
# della carta intestata (vedi letterhead_heights) quando la ragione sociale
# va a capo su più righe. Se quel CSS cambia, queste vanno tenute in sync.
# xhtml2pdf tratta i px CSS alla convenzione W3C degli 96dpi (1px = 0.75pt,
# vedi DPI96 in xhtml2pdf.util).
_PX_TO_PT = 0.75
_PAGE_MARGIN_PT = 1 * cm  # @page { margin: 1cm }
_POWERED_COL_WIDTH_PT = 96 * _PX_TO_PT  # .letterhead td.letterhead-powered { width: 96px }
_INFO_PADDING_LEFT_PT = 12 * _PX_TO_PT  # .letterhead td.letterhead-info { padding-left: 12px }
_INFO_PADDING_RIGHT_PT = 7 * _PX_TO_PT  # .letterhead td { padding: 4px 7px } (destra ereditata)
_INFO_PADDING_V_PT = 4 * _PX_TO_PT  # .letterhead td { padding: 4px 7px } (sopra/sotto)
_NAME_FONT_SIZE_PT = 14 * _PX_TO_PT  # .letterhead-name { font-size: 14px }
_EXTRA_FONT_SIZE_PT = 10 * _PX_TO_PT  # .letterhead-info { font-size: 10px }
_LINE_HEIGHT = 1.2  # .letterhead-info { line-height: 1.2 }
_BASE_HEIGHT_PT = 52 * _PX_TO_PT  # lato/altezza "storici" di logo e targhetta (52px), minimo su cui non si scende
_BASE_MARGIN_BOTTOM_PT = 14 * _PX_TO_PT  # .letterhead { margin: 0 0 14px 0 }
_MIN_MARGIN_BOTTOM_PT = 3 * _PX_TO_PT  # sotto non si scende: un minimo di respiro fra intestazione e resto
_MAX_ITERATIONS = 5  # il logo quadrato allarga la sua colonna, che restringe il testo: vedi _letterhead_height_pt


def _content_width_pt(page_width_pt: float, logo_width_pt: float) -> float:
  """Larghezza disponibile per il testo nella colonna centrale della carta
  intestata (components/company.html), dedotte le colonne di logo e
  targhetta powered e il padding della cella.

  Il padding va contato due volte, non una: verificato renderizzando la
  carta intestata vera e tracciando il valore di availWidth con cui
  xhtml2pdf chiama Paragraph.wrap() sulla cella (vedi scratchpad, script di
  calibrazione) - il padding dichiarato in CSS finisce sottratto sia dalla
  larghezza della colonna (TableStyle LEFTPADDING/RIGHTPADDING) sia di nuovo
  dentro il PmlKeepInFrame in cui xhtml2pdf avvolge il contenuto di ogni
  <td> (tables.py, pisaTagTD.end). Non e' un comportamento documentato di
  xhtml2pdf: se le classi .letterhead-info / .letterhead td in base.html
  cambiano padding, va rifatta la stessa verifica, non solo aggiornata la
  costante qui sotto."""
  table_width = page_width_pt - 2 * _PAGE_MARGIN_PT
  padding = _INFO_PADDING_LEFT_PT + _INFO_PADDING_RIGHT_PT
  return table_width - logo_width_pt - _POWERED_COL_WIDTH_PT - 2 * padding


def _paragraph_height_pt(text: str, font_name: str, font_size_pt: float, width_pt: float) -> float:
  """Quanto sarà alto (in pt) `text` una volta impaginato da reportlab dentro
  `width_pt`: stessa libreria di wrapping usata da xhtml2pdf per renderizzare
  il PDF vero, quindi il conto coincide con l'andare a capo reale."""
  style = ParagraphStyle('probe', fontName=font_name, fontSize=font_size_pt, leading=font_size_pt * _LINE_HEIGHT)
  _, height = Paragraph(xml_escape(text), style).wrap(width_pt, 10_000)
  return height


def _text_block_height_pt(company: Company, width_pt: float) -> float:
  """Altezza del solo testo (ragione sociale + indirizzo + P. IVA/C.F., senza
  il padding della cella) su `width_pt`, replicando il markup di
  company_header in components/company.html: stessi testi, stesso ordine,
  stessi font, altrimenti il conto e il rendering vero divergono
  silenziosamente."""
  name = company.legal_name or company.name
  height = _paragraph_height_pt(name, 'Helvetica-Bold', _NAME_FONT_SIZE_PT, width_pt)

  place = ', '.join(filter(None, [company.address, company.city]))
  ids = ' - '.join(
    filter(
      None,
      [
        f'P. IVA {company.vat_number}' if company.vat_number else None,
        f'C.F. {company.tax_code}' if company.tax_code else None,
      ],
    )
  )
  for line in filter(None, [place, ids]):
    height += _paragraph_height_pt(line, 'Helvetica', _EXTRA_FONT_SIZE_PT, width_pt)

  return height


def _letterhead_height_pt(company: Company, page_width_pt: float) -> float:
  """Altezza (in pt) della carta intestata su una pagina larga `page_width_pt`
  - e lato del logo, che va tenuto quadrato (vedi company_header in
  components/company.html): il logo non ha un'altezza fissa da riempire, è
  la riga stessa a doversi adattare a lui restando un quadrato, quindi
  quando cresce (nome che va a capo su più righe) allarga anche la sua
  colonna, restringendo quella del testo. Il conto quindi si richiama da
  solo: altezza -> larghezza testo -> a capo -> altezza. Converge in
  praticamente 1-2 iterazioni (la colonna del logo cresce di pochi pt, che
  di norma non bastano a spostare un ulteriore a capo), ma itera fino a
  _MAX_ITERATIONS per sicurezza invece di assumerlo."""
  height = _BASE_HEIGHT_PT
  for _ in range(_MAX_ITERATIONS):
    width = _content_width_pt(page_width_pt, logo_width_pt=height)
    text_height = _text_block_height_pt(company, width)
    new_height = max(_BASE_HEIGHT_PT, text_height + 2 * _INFO_PADDING_V_PT)
    if abs(new_height - height) < 0.01:
      return new_height
    height = new_height
  return height


def _letterhead_margin_bottom_pt(height_pt: float) -> float:
  """Margine sotto la carta intestata: si restringe esattamente di quanto
  l'intestazione e' crescita oltre la sua altezza storica, cosi' lo spazio
  totale "intestazione + margine" resta costante quale che sia la lunghezza
  della ragione sociale, invece di spingere il resto del documento in giu' e
  farlo sbordare su una pagina in piu' (i documenti RAE in particolare sono
  gia' compressi al millimetro per stare su una pagina sola, vedi i margini
  negativi in components/rae.html e .rae-h2/.rae-section in base.html)."""
  growth = height_pt - _BASE_HEIGHT_PT
  return max(_MIN_MARGIN_BOTTOM_PT, _BASE_MARGIN_BOTTOM_PT - growth)


def letterhead_heights(company: Company | None) -> dict:
  """Altezza e margine inferiore (in pt) a cui va forzata la carta
  intestata perché combaci sempre col blocco dati, invece di fluttuare
  centrata con vuoto sopra/sotto quando la ragione sociale va a capo su più
  righe (vedi company_header in components/company.html). Le due varianti
  servono perché lo stesso header compare anche sulle pagine orizzontali
  del borderò (schedules_report.html), dove la larghezza disponibile - e
  quindi l'a capo del testo - è diversa."""
  if not company:
    return {
      'letterhead_height_portrait': None,
      'letterhead_height_landscape': None,
      'letterhead_margin_bottom_portrait': None,
      'letterhead_margin_bottom_landscape': None,
    }
  height_portrait = _letterhead_height_pt(company, A4[0])
  height_landscape = _letterhead_height_pt(company, A4[1])
  return {
    'letterhead_height_portrait': height_portrait,
    'letterhead_height_landscape': height_landscape,
    'letterhead_margin_bottom_portrait': _letterhead_margin_bottom_pt(height_portrait),
    'letterhead_margin_bottom_landscape': _letterhead_margin_bottom_pt(height_landscape),
  }


def company_context() -> dict:
  """Intestazione aziendale per i template PDF: la company attiva, il suo
  logo, la targhetta "Powered by" e le altezze a cui vanno forzati perché
  combacino col blocco dati, già incorporati. Si spande nel render_template
  così ogni documento stampa la stessa carta intestata senza ripetere la
  logica."""
  company = get_active_company()
  return {
    'company': company,
    'company_logo': get_company_logo(company),
    'powered_tag': get_powered_tag(),
    **letterhead_heights(company),
  }


def _file_data_uri(path: str) -> str:
  mime = mimetypes.guess_type(path)[0] or 'image/png'
  with open(path, 'rb') as image_file:
    encoded = base64.b64encode(image_file.read()).decode('utf-8')
  return f'data:{mime};base64,{encoded}'


@lru_cache(maxsize=1)
def _ares_logo() -> str:
  return _file_data_uri(ARES_LOGO_PATH)


@lru_cache(maxsize=1)
def get_powered_tag() -> str:
  """Targhetta "Powered by Ares Logistics" come data URI.

  È un SVG e non testo HTML perché xhtml2pdf non supporta border-radius:
  gli angoli arrotondati si possono disegnare solo dentro l'immagine.
  """
  return _file_data_uri(POWERED_TAG_PATH)


def get_company_logo(company: Company | None) -> str:
  """Logo dell'attività come data URI, pronto per un <img> del PDF.

  xhtml2pdf gira senza link_callback: le immagini remote non le carica, come
  già per la firma. Il file dell'attività lo scriviamo noi in
  STATIC_FOLDER/company-logos e lo rileggiamo da lì; se non c'è (o non è ancora
  stato caricato) si ripiega sul logo Ares, che nella carta intestata è sempre
  presente.
  """
  if company and company.logo:
    path = get_full_path(STATIC_FOLDER, LOGO_SUBFOLDER, filename=os.path.basename(company.logo))
    if os.path.isfile(path):
      return _file_data_uri(path)

  return _ares_logo()


def get_signature(order: Order):
  if order.signature:
    signature_base64 = base64.b64encode(order.signature).decode('utf-8')
    return f'data:image/png;base64,{signature_base64}'
  else:
    return None


def get_signature_slots(order: Order) -> tuple[str | None, str | None]:
  """In quale blocco firme del PDF va mostrata la firma raccolta:
  - se l'ordine e' completato senza anomalie (DELIVERED e anomaly=False) va nel primo blocco
  - se l'ordine e' completato con anomalie (DELIVERED e anomaly=True) va nel blocco anomalie
  Ritorna (delivery_signature, anomaly_signature)."""
  signature = get_signature(order)
  if not signature:
    return None, None

  if order.status == OrderStatus.DELIVERED:
    if order.anomaly:
      return None, signature
    return signature, None

  return None, None


def export_pdf(document):
  response = make_response(document)
  response.headers['Content-Type'] = 'application/pdf'
  response.headers['Content-Disposition'] = 'inline; filename=report.pdf'
  return response


def export_excel(document):
  response = make_response(document)
  response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  response.headers['Content-Disposition'] = 'attachment; filename=report.xlsx'
  return response

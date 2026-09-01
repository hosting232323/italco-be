import os
import base64
import mimetypes
from functools import lru_cache
from flask import make_response

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


def company_context() -> dict:
  """Intestazione aziendale per i template PDF: la company attiva, il suo
  logo e la targhetta "Powered by" già incorporati. Si spande nel
  render_template così ogni documento stampa la stessa carta intestata
  senza ripetere la logica."""
  company = get_active_company()
  return {
    'company': company,
    'company_logo': get_company_logo(company),
    'powered_tag': get_powered_tag(),
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

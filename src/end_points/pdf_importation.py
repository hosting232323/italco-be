import re
import pdfplumber
from datetime import datetime
from flask import Blueprint,request

from database_api.operations import create, get_by_id
from .geographic_zone import get_cap_by_name
from ..database.schema import Order, Product, 
from ..database.enum import OrderType, OrderStatus, UserRole
from .users.session import flask_session_authentication


pdf_import_bp = Blueprint('pdf_import_bp', __name__)


@pdf_import_bp.route('/', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def order_import():
  testo = ''
  
  print(request.form['customer_id'])
  
  with pdfplumber.open('doc (28)_merged-1.pdf') as pdf:
    for pagina in pdf.pages:
      testo += pagina.extract_text() + '\n'
    order: Order = pdf_create_order(testo)
    pdf_create_product(pagina.extract_tables(), order.id)

  return {'status': 'ok'}


def pdf_create_product(tables, order_id: int):
  for table in tables:
    header = table[0]
    if header == [
      'Articolo',
      'Modello',
      'Tipologia - Descrizione',
      'Quantità - Peso Jg',
      'Servizio'
    ]:
      for row in table[1:]:
        create(Product, {
          'name': f'{row[0]} {row[1]} {row[2]}',
          'order_id': order_id,
          'service_user_id': 3,
          'collection_point_id': 3
        })
        # articolo = {
        #   'articolo': row[0],
        #   'modello': row[1],
        #   'descrizione': row[2],
        #   'quantita': int(quantita) if quantita else None,
        #   'peso_jg': float(peso) if peso else None,
        #   'servizio': row[4],
        # }


def pdf_create_order(testo):
  m_addressee = re.search(r'Destinatario:\s*(.+)', testo)
  addressee = m_addressee.group(1).strip() if m_addressee else None

  m_addressee_contact = re.search(r'Tel - Cell:\s*(\d+)', testo)
  addressee_contact = m_addressee_contact.group(1).strip() if m_addressee_contact else None

  address = None
  if addressee:
    m_address = re.search(r'Destinatario:.*\n(.+)', testo)
    if m_address:
      address = re.sub(r'Città\s*:\s*.+', '', m_address.group(1).strip()).strip()

      cities = re.findall(r'Città\s*:\s*(.+)', testo)
      city = cities[1].strip() if len(cities) > 1 else (cities[0].strip() if cities else None)
      city = re.sub(r'\bnd\b', '', city, flags=re.IGNORECASE).strip()

  m_dpc = re.search(r'Data consegna:\s*(\d{2}/\d{2}/\d{4})', testo)
  dpc = datetime.strptime(m_dpc.group(1).strip(), '%d/%m/%Y').date() if m_dpc else None

  return create(
    Order,
    {
      'status': OrderStatus.PENDING,
      'type': OrderType.DELIVERY,
      'addressee': addressee,
      'address': address,
      'addressee_contact': addressee_contact,
      'cap': get_cap_by_name(city),
      'dpc': dpc,
      'drc': datetime.now(),
    },
  )

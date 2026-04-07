import re
import pdfplumber
import camelot
from datetime import datetime

from database_api import Session
from ...utils.caps import get_cap_by_name
from database_api.operations import create
from ...database.enum import OrderType, OrderStatus
from ...database.schema import Order, Product, CollectionPoint
from ..service.queries import get_service_user_by_user_and_code

CITY_FIXES = {'Noic?ttaro': 'Noicattaro'}


def order_import_by_pdf(files, customer_id):
  collection_point = get_collection_point(customer_id)
  if not collection_point:
    return {'status': 'ko', 'error': 'Punto di ritiro non identificato'}

  orders_count = 0
  with Session() as session:
    for file in files.values():
      text = ''
      tables = []
      with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
          text += page.extract_text() + '\n'
          tables.extend(page.extract_tables())

      if not tables:
        camelot_tables = camelot.read_pdf(file, pages='all', flavor='stream')
        tables = [t.df.values.tolist() for t in camelot_tables]

      orders_count += 1
      order: Order = pdf_create_order(text, session=session)
      pdf_create_product(tables, text, order.id, collection_point.id, customer_id, session=session)

    session.commit()
  return {'status': 'ok', 'imported_orders_count': orders_count}


def pdf_create_product(tables, text, order_id: int, collection_point_id: int, user_id: int, session):
  products = []

  if tables:
    for table in tables:
      header = table[0]
      if header == ['Articolo', 'Modello', 'Tipologia - Descrizione', 'Quantità - Peso Jg', 'Servizio']:
        for row in table[1:]:
          products.append(
            {'articolo': row[0], 'modello': row[1], 'descrizione': row[2], 'quantita': row[3], 'servizio': row[4]}
          )

  for p in products:
    service_user = get_service_user_by_user_and_code(user_id, p['servizio'].strip(), session=session)
    create(
      Product,
      {
        'order_id': order_id,
        'name': f'{p["articolo"]} {p["modello"]} {p["descrizione"]}',
        'collection_point_id': collection_point_id,
        'service_user_id': service_user.id if service_user else None
      },
      session=session,
    )


def pdf_create_order(text, session):
  m_addressee = re.search(r'Destinatario:\s*(.+)', text)
  addressee = m_addressee.group(1).strip() if m_addressee else None

  m_addressee_contact = re.search(r'Tel - Cell:\s*(\d+)', text)
  addressee_contact = m_addressee_contact.group(1).strip() if m_addressee_contact else None

  address = None
  city = None
  if addressee:
    m_address = re.search(r'Destinatario:.*\n(.+)', text)
    if m_address:
      address = re.sub(r'Città\s*:\s*.+', '', m_address.group(1).strip()).strip()

      cities = re.findall(r'Città\s*:\s*(.+)', text)
      city = cities[1].strip() if len(cities) > 1 else (cities[0].strip() if cities else None)
      city = re.sub(r'\bnd\b', '', city, flags=re.IGNORECASE).strip()
      city = normalize_city(city)

  m_dpc = re.search(r'Data consegna:\s*(\d{2}/\d{2}/\d{4})', text)
  dpc = datetime.strptime(m_dpc.group(1).strip(), '%d/%m/%Y').date() if m_dpc else None

  return create(
    Order,
    {
      'dpc': dpc,
      'address': address,
      'drc': datetime.now(),
      'addressee': addressee,
      'type': OrderType.DELIVERY,
      'cap': get_cap_by_name(city),
      'status': OrderStatus.ACQUIRED,
      'addressee_contact': addressee_contact,
    },
    session=session,
  )


def get_collection_point(customer_id: int) -> CollectionPoint:
  with Session() as session:
    return session.query(CollectionPoint).filter(CollectionPoint.user_id == customer_id).first()


def normalize_city(city: str) -> str:
  city_clean = city.strip() if city else ''
  return CITY_FIXES.get(city_clean, city_clean)

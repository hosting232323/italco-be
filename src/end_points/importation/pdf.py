import re
import pdfplumber
from datetime import datetime
from sqlalchemy.orm import Session as session_type

from database_api import Session
from ...utils.caps import get_cap_by_name
from database_api.operations import create
from ...database.enum import OrderType, OrderStatus
from ...database.schema import Order, Product, CollectionPoint, ServiceUser


CITY_FIXES = {
  "noic?ttaro": "noicattaro"
}

def order_import_by_pdf(files, customer_id):
  collection_point = get_collection_point(customer_id)
  if not collection_point:
    return {'status': 'ko', 'error': 'Punto di ritiro non identificato'}

  text = ''
  orders_count = 0
  with Session() as session:
    for file in files.values():
      with pdfplumber.open(file) as pdf:
        for pagina in pdf.pages:
          text += pagina.extract_text() + '\n'

        orders_count += 1
        order: Order = pdf_create_order(text, session=session)
        pdf_create_product(pagina.extract_tables(), order.id, collection_point.id, customer_id, session=session)

    session.commit()
  return {'status': 'ok', 'imported_orders_count': orders_count}


def pdf_create_product(tables, order_id: int, collection_point_id: int, user_id: int, session):
  for table in tables:
    header = table[0]
    if header == ['Articolo', 'Modello', 'Tipologia - Descrizione', 'Quantità - Peso Jg', 'Servizio']:
      for row in table[1:]:
        service_user = get_service_user(user_id, row[4], session=session)
        create(
          Product,
          {
            'order_id': order_id,
            'service_user_id': service_user.id,
            'name': f'{row[0]} {row[1]} {row[2]}',
            'collection_point_id': collection_point_id,
          },
          session=session,
        )


def pdf_create_order(text, session):
  m_addressee = re.search(r'Destinatario:\s*(.+)', text)
  addressee = m_addressee.group(1).strip() if m_addressee else None

  m_addressee_contact = re.search(r'Tel - Cell:\s*(\d+)', text)
  addressee_contact = m_addressee_contact.group(1).strip() if m_addressee_contact else None

  address = None
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
      'status': OrderStatus.PENDING,
      'addressee_contact': addressee_contact,
    },
    session=session,
  )


def get_collection_point(customer_id: int) -> CollectionPoint:
  with Session() as session:
    return session.query(CollectionPoint).filter(CollectionPoint.user_id == customer_id).first()


def get_service_user(user_id: int, code: str, session: session_type) -> ServiceUser:
  return session.query(ServiceUser).filter(ServiceUser.user_id == user_id, ServiceUser.code == code).first()


def normalize_city(city: str) -> str:
  city_clean = city.lower().strip()
  return CITY_FIXES.get(city_clean, city_clean)

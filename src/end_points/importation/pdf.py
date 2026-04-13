import re
import camelot
import pdfplumber
from datetime import datetime

from database_api import Session
from ...utils.caps import get_cap_by_name
from database_api.operations import create
from ...database.enum import OrderType, OrderStatus
from ...database.schema import Order, Product, CollectionPoint
from ..service.queries import get_service_user_by_user_and_code


CITY_FIXES = {
  'Noic?ttaro': 'Noicattaro',
  'BARI-CARBONARA Bari': 'Carbonara',
}


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
        tables = [table.df.values.tolist() for table in camelot.read_pdf(file, pages='all', flavor='stream')]

      orders_count += 1
      order = pdf_create_order(text, session=session)
      pdf_create_product(tables, order.id, collection_point.id, customer_id, session=session)

    session.commit()
  return {'status': 'ok', 'imported_orders_count': orders_count}


def pdf_create_product(tables, order_id: int, collection_point_id: int, user_id: int, session):
  if tables:
    for table in tables:
      if table[0] == ['Articolo', 'Modello', 'Tipologia - Descrizione', 'Quantità - Peso Jg', 'Servizio']:
        for row in table[1:]:
          create(
            Product,
            {
              'order_id': order_id,
              'name': f'{row[0]} {row[1]} {row[2]}',
              'collection_point_id': collection_point_id,
              'service_user_id': get_service_user_by_user_and_code(user_id, row[4], session=session).id,
            },
            session=session,
          )


def pdf_create_order(text, session) -> Order:
  city = re.findall(r'Città\s*:\s*(.+)', text)
  city = (
    normalize_city(
      re.sub(r'\bnd\b', '', city[1].strip() if len(city) > 1 else city[0].strip(), flags=re.IGNORECASE).strip()
    )
    if city
    else None
  )
  address = re.search(r'Destinatario:.*\n(.+)', text)
  address = re.sub(r'Città\s*:\s*.+', '', address.group(1).strip()).strip() if address else None
  addressee = re.search(r'Destinatario:\s*(.+)', text)
  addressee_contact = re.search(r'Tel - Cell:\s*(\d+)', text)
  dpc = re.search(r'Data consegna:\s*(\d{2}/\d{2}/\d{4})', text)

  return create(
    Order,
    {
      'drc': datetime.now(),
      'type': OrderType.DELIVERY,
      'cap': get_cap_by_name(city),
      'status': OrderStatus.ACQUIRED,
      'address': f'{address}, {city}',
      'addressee': addressee.group(1).strip() if addressee else None,
      'dpc': datetime.strptime(dpc.group(1).strip(), '%d/%m/%Y').date() if dpc else None,
      'addressee_contact': addressee_contact.group(1).strip() if addressee_contact else None,
    },
    session=session,
  )


def normalize_city(city: str) -> str:
  city_clean = city.strip()
  return CITY_FIXES.get(city_clean, city_clean)


def get_collection_point(customer_id: int) -> CollectionPoint:
  with Session() as session:
    return session.query(CollectionPoint).filter(CollectionPoint.user_id == customer_id).first()

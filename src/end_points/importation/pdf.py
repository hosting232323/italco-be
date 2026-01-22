import re
import pdfplumber
from datetime import datetime

from database_api import Session
from database_api.operations import create
from ..geographic_zone import get_cap_by_name
from ...database.enum import OrderType, OrderStatus
from ...database.schema import Order, Product, CollectionPoint, ServiceUser


def order_import_by_pdf(files, customer_id):
  text = ''
  orders_count = 0
  for file in files.values():
    with pdfplumber.open(file) as pdf:
      for pagina in pdf.pages:
        text += pagina.extract_text() + '\n'

      orders_count += 1
      order: Order = pdf_create_order(text)
      pdf_create_product(
        pagina.extract_tables(),
        order.id,
        get_collection_point(customer_id).id,
        customer_id,
      )

  return {'status': 'ok', 'imported_orders_count': orders_count}


def pdf_create_product(tables, order_id: int, collection_point_id: int, user_id: int):
  for table in tables:
    header = table[0]
    if header == ['Articolo', 'Modello', 'Tipologia - Descrizione', 'Quantità - Peso Jg', 'Servizio']:
      for row in table[1:]:
        service_user = get_service_user(user_id, row[4])
        create(
          Product,
          {
            'name': f'{row[0]} {row[1]} {row[2]}',
            'order_id': order_id,
            'service_user_id': service_user.id,
            'collection_point_id': collection_point_id,
          },
        )


def pdf_create_order(text):
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

  m_dpc = re.search(r'Data consegna:\s*(\d{2}/\d{2}/\d{4})', text)
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


def get_collection_point(customer_id: int) -> CollectionPoint:
  with Session() as session:
    return session.query(CollectionPoint).filter(CollectionPoint.user_id == customer_id).first()


def get_service_user(user_id: int, code: str) -> ServiceUser:
  with Session() as session:
    return session.query(ServiceUser).filter(ServiceUser.user_id == user_id).filter(ServiceUser.code == code).first()

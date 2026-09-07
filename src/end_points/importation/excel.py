from ...order_integrity import split_order_by_service_type, lock_order_service_integrity

import re

import pandas as pd
from sqlalchemy import func
from collections import defaultdict

from database_api import Session
from database_api.operations import create
from ..service.queries import get_service_users
from ...database.enum import OrderType, OrderStatus
from ...database.schema import Order, Product, CollectionPoint, ServiceUser


REQUIRED_COLUMNS = [
  'Rif. Com',
  'Cod.  Serv',
  'Descr. Serv',
  'LDP',
  'Destinatario',
  'Indirizzo Dest.',
  'Localita',
  'Provincia',
  'CAP',
  'Booking',
  'DRC',
  'Piano',
  'Note MW + Note',
]

# Un Piano valido e' un intero: '2' e '2.0' sono lo stesso piano, '1.5' non e' un piano.
FLOOR_INTEGER = re.compile(r'^\d+(\.0+)?$')

# Campi del payload di conflitto letti da build_order.
BUILD_ORDER_FIELDS = [
  'Rif. Com',
  'Destinatario',
  'Indirizzo Dest.',
  'Localita',
  'Provincia',
  'CAP',
  'Booking',
  'DRC',
  'Piano',
  'Note MW + Note',
]

DATE_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}')


def validate_conflict_order(order_data, session, customer_id=None) -> str:
  """Valida struttura, campi e riferimenti di un ordine del conflict prima di
  toccare il DB. Ritorna il messaggio d'errore per failed_orders, o None."""
  if not isinstance(order_data, dict):
    return 'Ordine in formato non valido'

  missing_fields = [field for field in BUILD_ORDER_FIELDS if field not in order_data]
  if missing_fields:
    return 'Campi ordine mancanti: ' + ', '.join(missing_fields)

  for field in ('Booking', 'DRC'):
    if not isinstance(order_data[field], str) or not DATE_PATTERN.match(order_data[field]):
      return f'Data "{field}" non valida'

  products = order_data.get('products')
  if not isinstance(products, dict) or len(products) == 0:
    return 'Prodotti mancanti o in formato non valido'

  customer_ids = set()
  for product_name, product in products.items():
    if not isinstance(product, dict):
      return f'Prodotto "{product_name}" in formato non valido'

    services = product.get('services')
    if not isinstance(services, list) or len(services) == 0:
      return f'Servizi mancanti o non validi per il prodotto "{product_name}"'

    if not all(isinstance(service_user_id, int) for service_user_id in services):
      return f'Servizi mancanti o non validi per il prodotto "{product_name}"'

    collection_point = product.get('collection_point')
    if not isinstance(collection_point, dict) or not isinstance(collection_point.get('id'), int):
      return f'Punto di ritiro mancante per il prodotto "{product_name}"'

    if session.query(ServiceUser.id).filter(ServiceUser.id.in_(services)).count() != len(set(services)):
      return f'Servizi inesistenti per il prodotto "{product_name}"'

    point = session.query(CollectionPoint).filter(CollectionPoint.id == collection_point['id']).first()
    if point is None:
      return f'Punto di ritiro inesistente per il prodotto "{product_name}"'
    owners = {row.user_id for row in session.query(ServiceUser).filter(ServiceUser.id.in_(services)).all()}
    customer_ids.update(owners)
    if owners != {point.user_id}:
      return f'Servizi e punto di ritiro di clienti differenti per il prodotto "{product_name}"'

  if len(customer_ids) != 1 or (customer_id is not None and customer_ids != {int(customer_id)}):
    return 'I servizi devono appartenere tutti al punto vendita selezionato'

  return None


def order_import_by_excel(file, customer_id):
  conflicted_orders = []
  imported_orders_count = 0
  orders, error = parse_orders(file, customer_id)
  if error:
    return {'status': 'ko', 'message': error}

  for _, order_data in orders.items():
    if (
      len(order_data['products']) != 1
      or len(order_data['services']) == 0
      or any(not product['collection_point'] for product in order_data['products'])
    ):
      conflicted_orders.append(
        {
          **order_data['rows'][0].to_dict(),
          'services': order_data['services'],
          'products': {
            product['name']: {
              'services': [],
              'collection_point': product['collection_point'].to_dict() if product['collection_point'] else None,
            }
            for product in order_data['products']
          },
        }
      )
      continue

    with Session() as session:
      lock_order_service_integrity(session)
      order = create(Order, build_order(order_data['rows'][0]), session=session)
      for service_user in order_data['services']:
        create(
          Product,
          {
            'order_id': order.id,
            'service_user_id': service_user['id'],
            'name': order_data['products'][0]['name'],
            'collection_point_id': order_data['products'][0]['collection_point'].id,
          },
          session=session,
        )
      created_orders = split_order_by_service_type(order, session)
      session.commit()
    imported_orders_count += len(created_orders)
  return {'status': 'ok', 'imported_orders_count': imported_orders_count, 'conflicted_orders': conflicted_orders}


def handle_excel_conflict(orders, customer_id=None):
  failed_orders = []
  imported_orders_count = 0
  for order_data in orders:
    with Session() as session:
      lock_order_service_integrity(session)
      error = validate_conflict_order(order_data, session, customer_id=customer_id)
      if error:
        external_id = order_data.get('Rif. Com') if isinstance(order_data, dict) else None
        failed_orders.append({'external_id': external_id, 'error': error})
        continue

      order = create(Order, build_order(order_data), session=session)
      for product_name, product in order_data['products'].items():
        for service_user_id in product['services']:
          create(
            Product,
            {
              'name': product_name,
              'order_id': order.id,
              'service_user_id': service_user_id,
              'collection_point_id': product['collection_point']['id'],
            },
            session=session,
          )
      created_orders = split_order_by_service_type(order, session)
      session.commit()
    imported_orders_count += len(created_orders)
  return {'status': 'ok', 'imported_orders_count': imported_orders_count, 'failed_orders': failed_orders}


def parse_orders(file, customer_id):
  service_users = get_service_users(customer_id)
  df = pd.read_excel(file, dtype=str).fillna('')
  df.columns = [c.strip() for c in df.columns]

  missing_columns = [column for column in REQUIRED_COLUMNS if column not in df.columns]
  if missing_columns:
    return None, 'Il file Excel non ha il formato atteso. Colonne mancanti: ' + ', '.join(missing_columns) + '.'

  orders = defaultdict(lambda: {'products': [], 'services': [], 'rows': []})
  for _, row in df.iterrows():
    if row['Cod.  Serv'] in ['', '404']:
      continue

    orders[row['Rif. Com']]['rows'].append(row)
    service_user = next(
      (service_user for service_user in service_users if service_user.code == row['Cod.  Serv']), None
    )
    if service_user:
      orders[row['Rif. Com']]['services'].append({'id': service_user.id, 'name': row['Descr. Serv']})
    else:
      orders[row['Rif. Com']]['products'].append(
        {
          'name': row['Descr. Serv'],
          'collection_point': get_collection_point(row['LDP'], customer_id),
        }
      )
  return orders, None


def parse_floor(value) -> int:
  """Ritorna il Piano come intero, oppure None se non lo e' gia'.

  Il foglio e' compilato a mano e `read_excel(dtype=str)` consegna ogni cella
  come stringa: 'PT', '1,5' o un decimale non sono piani, e su `Order.floor`,
  che e' una colonna intera, farebbero fallire l'INSERT. Il ciclo di import non
  gestisce l'eccezione, quindi una sola cella cosi' interrompe l'importazione
  dopo gli ordini gia' committati. Il valore viene scartato e non reinterpretato:
  meglio un piano mancante, che l'operatore vede e corregge, di un piano
  inventato arrotondando.
  """
  text = str(value).strip() if value is not None else ''
  if not FLOOR_INTEGER.match(text):
    return None

  return int(text.split('.')[0])


def build_order(order: dict):
  return {
    'type': OrderType.DELIVERY,
    'status': OrderStatus.ACQUIRED,
    'addressee': order['Destinatario'],
    'address': f'{order["Indirizzo Dest."]}, {order["Localita"]}, {order["Provincia"]}',
    'cap': order['CAP'],
    'dpc': order['Booking'],
    'drc': order['DRC'],
    'floor': parse_floor(order['Piano']),
    'operator_note': 'Ordine importato da file',
    'customer_note': order['Note MW + Note'],
    'external_id': order['Rif. Com'],
  }


def get_collection_point(name: str, customer_id: int) -> CollectionPoint:
  with Session() as session:
    return (
      session.query(CollectionPoint)
      .filter(CollectionPoint.user_id == customer_id, func.trim(CollectionPoint.name) == name.strip())
      .first()
    )

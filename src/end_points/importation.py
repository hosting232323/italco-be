import pandas as pd
from sqlalchemy import func
from collections import defaultdict
from flask import Blueprint, request

from database_api import Session
from database_api.operations import create
from .service.queries import get_service_users
from .users.session import flask_session_authentication
from ..database.enum import UserRole, OrderType, OrderStatus
from ..database.schema import User, Order, Product, CollectionPoint


import_bp = Blueprint('import_bp', __name__)


@import_bp.route('', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def order_import(user: User):
  if 'file' not in request.files:
    return {'status': 'ko', 'error': 'Nessun file caricato'}

  conflicted_orders = []
  imported_orders_count = 0
  orders = parse_orders(request.files['file'], request.form['customer_id'])
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

    order = create(Order, build_order(order_data['rows'][0]))
    for service_user in order_data['services']:
      create(
        Product,
        {
          'order_id': order.id,
          'service_user_id': service_user['id'],
          'name': order_data['products'][0]['name'],
          'collection_point_id': order_data['products'][0]['collection_point'].id,
        },
      )
    imported_orders_count += 1
  return {'status': 'ok', 'imported_orders_count': imported_orders_count, 'conflicted_orders': conflicted_orders}


@import_bp.route('conflict', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def handle_conflict(user: User):
  imported_orders_count = 0
  for order_data in request.json['orders']:
    order = create(Order, build_order(order_data))
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
        )
    imported_orders_count += 1
  return {'status': 'ok', 'imported_orders_count': imported_orders_count}


def parse_orders(file, customer_id):
  service_users = get_service_users(customer_id)
  df = pd.read_excel(file, dtype=str).fillna('')
  df.columns = [c.strip() for c in df.columns]
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
  return orders


def build_order(order: dict):
  return {
    'type': OrderType.DELIVERY,
    'status': OrderStatus.PENDING,
    'addressee': order['Destinatario'],
    'address': f'{order["Indirizzo Dest."]}, {order["Localita"]}, {order["Provincia"]}',
    'cap': order['CAP'],
    'dpc': order['DPC'],
    'drc': order['DRC'],
    'floor': order['Piano'],
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

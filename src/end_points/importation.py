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
    if len(order_data['products']) != 1 or len(order_data['services']) == 0:
      conflicted_orders.append(
        {
          **order_data['rows'][0].to_dict(),
          'services': order_data['services'],
          'products': {product: [] for product in order_data['products']},
        }
      )
      continue

    order = create(Order, build_order(order_data['rows'][0], request.form['customer_id']))
    for service_user in order_data['services']:
      create(
        Product,
        {'order_id': order.id, 'service_user_id': service_user['id'], 'product': order_data['products'][0]},
      )
    imported_orders_count += 1
  return {'status': 'ok', 'imported_orders_count': imported_orders_count, 'conflicted_orders': conflicted_orders}


@import_bp.route('conflict', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def handle_conflict(user: User):
  imported_orders_count = 0
  for order_data in request.json['orders']:
    order = create(Order, build_order(order_data, request.json['customer_id']))
    for product, service_user_ids in order_data['products'].items():
      for service_user_id in service_user_ids:
        create(Product, {'product': product, 'order_id': order.id, 'service_user_id': service_user_id})
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
      orders[row['Rif. Com']]['products'].append(row['Descr. Serv'])
  return orders


def build_order(order: dict, customer_id: int):
  with Session() as session:
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
      'collection_point_id': session.query(CollectionPoint.id)
      .filter(CollectionPoint.user_id == customer_id, func.trim(CollectionPoint.name) == order['LDP'].strip())
      .scalar(),
    }

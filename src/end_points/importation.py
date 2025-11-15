import pandas as pd
from collections import defaultdict
from flask import Blueprint, request

from database_api import Session
from database_api.operations import create
from .users.session import flask_session_authentication
from ..database.enum import UserRole, OrderType, OrderStatus
from ..database.schema import User, Order, OrderServiceUser, ServiceUser


PRODUCT_NOTE = 'Ordine importato da file'
import_bp = Blueprint('import_bp', __name__)


@import_bp.route('', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def order_import(user: User):
  if 'file' not in request.files:
    return {'status': 'ko', 'error': 'Nessun file caricato'}

  conflicted_orders = {}
  imported_orders_count = 0
  orders = parse_orders(request.files['file'], request.form['customer_id'])
  for order_ref, order_data in orders.items():
    if len(order_data['products']) > 1:
      conflicted_orders[order_ref] = order_data['rows']
      continue

    order = create(Order, {
      'type': OrderType.DELIVERY,
      'status': OrderStatus.PENDING,
      'operator_note': PRODUCT_NOTE
    })
    for service_user_id in order_data['services']:
      create(OrderServiceUser, {
        'order_id': order.id,
        'service_user_id': service_user_id,
        'product': order_data['products'][0]
      })
    imported_orders_count += 1
  return {'status': 'ok', 'imported_orders_count': imported_orders_count, 'conflicted_orders': conflicted_orders}


@import_bp.route('conflict', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def handle_conflict(user: User):
  imported_orders_count = 0
  for order in request.json['orders']:
    new_order = create(Order, {
      'type': OrderType.DELIVERY,
      'status': OrderStatus.PENDING,
      'operator_note': PRODUCT_NOTE
    })
    for product, service_user_id in order['products'].items():
      create(OrderServiceUser, {
        'product': product,
        'order_id': new_order.id,
        'service_user_id': service_user_id
      })
    imported_orders_count += 1
  return {'status': 'ok', 'imported_orders_count': imported_orders_count}


def parse_orders(file, customer_id):
  service_users = get_service_users(customer_id)
  df = pd.read_excel(file)
  df.columns = [c.strip() for c in df.columns]
  orders = defaultdict(lambda: {'products': [], 'services': [], 'rows': []})
  for _, row in df.iterrows():
    if row['Cos. Serv'] != 404:
      continue

    orders[row['Rif. Com']]['rows'].append(row)
    service_user = next((
      service_user for service_user in service_users if service_user.code == row['Cos. Serv']
    ), None)
    if service_user:
      orders[row['Rif. Com']]['services'].append(service_user.id)
    else:
      orders[row['Rif. Com']]['products'].append(row['Descr. Serv'])
  return orders


def get_service_users(user_id: int) -> list[ServiceUser]:
  with Session() as session:
    return session.query(ServiceUser).filter(ServiceUser.user_id == user_id).all()

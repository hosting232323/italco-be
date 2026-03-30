import os
import csv
from tqdm import tqdm
from sqlalchemy import and_
from datetime import datetime
from collections import defaultdict

from database_api import set_database, Session
from src.database.schema import Order, Product, ServiceUser, Service, User, OrderStatus


def get_orders():
  with Session() as session:
    return session.query(
      Order, Product, Service
    ).join(
      Product, and_(
        Order.id == Product.order_id,
        Order.status == OrderStatus.DELIVERED,
        Order.booking_date.between(datetime(2026, 2, 1), datetime(2026, 2, 28, 23, 59, 59))
      )
    ).join(
      ServiceUser, Product.service_user_id == ServiceUser.id
    ).join(
      Service, ServiceUser.service_id == Service.id
    ).join(
      User, and_(ServiceUser.user_id == User.id, User.nickname == 'Euronics Bari Max')
    ).all()


def aggregate_orders(rows: list[tuple[Order, Product, Service]]):
  orders = defaultdict(lambda: {
    'id': None,
    'external_id': None,
    'created_at': None,
    'addressee': None,
    'products': list(),
    'services': list()
  })

  for row in rows:
    order = orders[row[0].id]
    order['id'] = row[0].id
    order['external_id'] = row[0].external_id
    order['created_at'] = row[0].created_at
    order['addressee'] = row[0].addressee
    if row[1]:
      order['products'].append(row[1].name)
    if row[2]:
      order['services'].append(row[2].name)
  return orders.values()


def write_csv(orders, filename='orders.csv'):
  with open(filename, mode='w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow([
      'id',
      'external_id',
      'created_at',
      'products',
      'services',
      'addressee'
    ])

    for order in tqdm(orders):
      writer.writerow([
        order['id'],
        order['external_id'],
        order['created_at'],
        order['addressee'],
        ', '.join(order['products']),
        ', '.join(order['services']),
      ])


if __name__ == '__main__':
  set_database(os.environ['DATABASE_URL'])
  rows = []
  for row in tqdm(get_orders()):
    rows.append(row)
  aggregated_orders = aggregate_orders(rows)
  write_csv(aggregated_orders)
  print('CSV generato con successo ✅')

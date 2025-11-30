import os
import pandas as pd
from tqdm import tqdm
from sqlalchemy import and_

from database_api import set_database, Session
from src.database.schema import Order, Product, Service, ServiceUser
from database_api.operations import create, get_by_id, delete


FILE_PATH = ''
ID_ROW_LABEL = 'ID'
PRODUCT_ROW_LABEL = 'Prodotto'
SERVICE_ROW_LABEL = 'Servizio'
CUSTOMER_USER_ID = ''
COLLECTION_POINT_ID = ''


def get_products(order: Order) -> list[Product]:
  with Session() as session:
    return session.query(Product).filter(Product.order_id == order).all()


def get_service_user(service_name: str) -> ServiceUser:
  with Session() as session:
    return session.query(ServiceUser).join(Service, and_(
      ServiceUser.user_id == CUSTOMER_USER_ID,
      Service.name == service_name,
      ServiceUser.service_id == Service.id
    )).first()


if __name__ == '__main__':
  set_database(os.environ['DATABASE_URL'])
  df = pd.read_excel(FILE_PATH, dtype=str).fillna('')
  df.columns = [c.strip() for c in df.columns]
  orders = {}
  for _, row in df.iterrows():
    id = int(row[ID_ROW_LABEL])
    if id not in orders:
      orders[id] = {row[PRODUCT_ROW_LABEL]: [row[SERVICE_ROW_LABEL]]}
    elif row[PRODUCT_ROW_LABEL] not in orders[id]:
      orders[id][row[PRODUCT_ROW_LABEL]] = [row[SERVICE_ROW_LABEL]]
    elif row[SERVICE_ROW_LABEL] not in orders[id][row[PRODUCT_ROW_LABEL]]:
      orders[id][row[PRODUCT_ROW_LABEL]].append(row[SERVICE_ROW_LABEL])
    else:
      print(f'Riga duplicata {id} {row[PRODUCT_ROW_LABEL]} {row[SERVICE_ROW_LABEL]}')

  for order_id in tqdm(orders.keys()):
    order = get_by_id(Order, order_id)
    if not order:
      print(f'Non trovato ordine con id {order_id}')
      continue

    for product in get_products(order):
      delete(product)

    for product in orders[order_id].keys():
      for service_name in order[order_id][product]:
        service = get_service_user(service_name)
        if not service:
          print(f'Non trovato servizio con nome {service_name}')
          continue

        create(Product, {
          'name': product,
          'order_id': order_id,
          'service_user_id': service.id,
          'collection_point_id': COLLECTION_POINT_ID
        })

import os
import random
import requests
import traceback
from apscheduler.triggers.cron import CronTrigger
from apscheduler.schedulers.background import BackgroundScheduler

from api.settings import IS_DEV
from api import send_telegram_error
from database_api.operations import create
from .database.enum import OrderType, OrderStatus
from .database.schema import Order, Product, User, CollectionPoint
from .end_points.service.queries import get_service_user_by_user_and_code
from .end_points.users.queries import get_user_and_collection_point_by_code
from .end_points.orders.queries import get_order_by_external_id_and_customer


EURONICS_API_PASSWORD = os.environ.get('EURONICS_API_PASSWORD', None)


def start_scheduler():
  if not IS_DEV and EURONICS_API_PASSWORD:
    scheduler = BackgroundScheduler()
    scheduler.add_job(
      save_orders_by_euronics,
      trigger=CronTrigger(second='*/15', hour='9-17', day_of_week='mon-sat'),
      id='euronics_api',
      replace_existing=True,
    )
    scheduler.start()


def save_orders_by_euronics():
  try:
    for imported_order in call_euronics_api():
      user, collection_point = get_user_and_collection_point_by_code(imported_order['cod_pv'])
      if not user:
        raise ValueError('Punto vendita non riconosciuto')

      if get_order_by_external_id_and_customer(imported_order['id_vendita'], user.id):
        continue

      product_service_user_handler(
        imported_order,
        user,
        collection_point,
        create(
          Order,
          {
            'type': OrderType.DELIVERY,
            'cap': imported_order['cap'],
            'status': OrderStatus.PENDING,
            'drc': imported_order['data_vendita'],
            'addresse': imported_order['cliente'],
            'dpc': imported_order['data_consegna'],
            'external_id': imported_order['id_vendita'],
            'addressee_contact': f'{imported_order["telefono"]} {imported_order["telefono1"]}',
            'address': f'{imported_order["indirizzo"]} {imported_order["localita"]} {imported_order["provincia"]}',
          },
        ),
      )
  except Exception:
    traceback.print_exc()
    send_telegram_error(traceback.format_exc(), endpoint=False)
    return {'status': 'ko', 'error': 'Errore generico'}


def product_service_user_handler(
  imported_order: dict, user: User, collection_point: CollectionPoint, created_order: Order
):
  products = []
  service_users = []
  for item in imported_order['dettaglio']:
    service_user = get_service_user_by_user_and_code(user.id, item['cod_articolo'])
    if service_user:
      service_users.append(service_user)
    else:
      products.append({'name': imported_order['descrizione'], 'services': []})

  if len(products) > len(service_users):
    raise ValueError('Servizi e prodotti non utilizzabili')

  if len(products) == 1:
    products[0]['services'] = service_users
  else:
    for product, service in zip(products, service_users):
      product['services'].append(service)
    remaining_services = service_users[len(products) :]
    for service in remaining_services:
      random.choice(products)['services'].append(service)

  for product in products:
    for service_user in product['services']:
      create(
        Product,
        {
          'name': product['name'],
          'order_id': created_order.id,
          'service_user_id': service_users.id,
          'collection_point_id': collection_point.id,
        },
      )


def call_euronics_api():
  return requests.get(
    f'https://delivery.siemdistribuzione.it/Api/DeliveryVettoriAPI/ListaConsegne/?user=logisco&pwd={EURONICS_API_PASSWORD}'
  ).json()

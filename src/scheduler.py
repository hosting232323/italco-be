import requests
import traceback
from apscheduler.triggers.cron import CronTrigger
from apscheduler.schedulers.background import BackgroundScheduler

from api import send_telegram_error
from database_api.operations import create
from .database.schema import Order, Product
from .database.enum import OrderType, OrderStatus
from .end_points.service.queries import get_service_user_by_user_and_code


def start_scheduler():
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
      created_order = create(
        Order,
        {
          'type': OrderType.DELIVERY,
          'cap': imported_order['cap'],
          'status': OrderStatus.PENDING,
          'addresse': imported_order['cliente'],
          'address': f'{imported_order["indirizzo"]} {imported_order["localita"]} {imported_order["provincia"]}',
          'addressee_contact': imported_order['telefono']
          if imported_order['telefono'] != ''
          else imported_order['telefono1'],
        },
      )
      for product in imported_order['dettaglio']:
        create(
          Product,
          {
            'order_id': created_order.id,
            'service_user_id': get_service_user_by_user_and_code('', product['descrizione']).id,
          },
        )
  except Exception:
    traceback.print_exc()
    send_telegram_error(traceback.format_exc(), endpoint=False)
    return {'status': 'ko', 'error': 'Errore generico'}


def call_euronics_api():
  return requests.get('url')

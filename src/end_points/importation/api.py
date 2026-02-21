import random
import requests
from datetime import datetime, timedelta

from database_api import Session
from ... import EURONICS_API_PASSWORD
from database_api.operations import create, update
from ...database.enum import OrderType, OrderStatus
from ..service.queries import get_service_user_by_user_and_code
from ..users.queries import get_user_and_collection_point_by_code
from ...database.schema import Order, Product, User, CollectionPoint
from ..orders.queries import get_order_by_external_id_and_customer, get_order_by_external_id


ORDER_STATUS_MAP = {
  0: OrderStatus.NEW,
  1: OrderStatus.CONFIRMED,
  2: OrderStatus.NOT_DELIVERED,
  3: OrderStatus.BOOKING,
  4: OrderStatus.CONFIRMED,
  8: OrderStatus.REPLACEMENT,
  9: OrderStatus.REDELIVERY,
  10: OrderStatus.CANCELLED,
  11: OrderStatus.URGENT,
  12: OrderStatus.VERIFICATION,
  13: OrderStatus.CANCELLED_TO_BE_REFUNDED,
  100: OrderStatus.DELETED,
}


def save_orders_by_euronics():
  if not EURONICS_API_PASSWORD:
    return {'status': 'ko', 'message': 'Api Key Error'}

  for imported_order in call_list_euronics_api():
    result = get_user_and_collection_point_by_code(imported_order['cod_pv'])
    if not result or not result[0]:
      print(f'Non trovato punto vendita {imported_order["cod_pv"]}')
      continue

    external_status = ORDER_STATUS_MAP[imported_order['stato']]
    order = get_order_by_external_id_and_customer(imported_order['id_consegna'], result[0].id)
    if order:
      if order.external_status != external_status or (
        imported_order['dataconferma'] != '' and imported_order['dataconferma'] != order.confirmation_date
      ):
        update(
          order, {'external_status': external_status, 'confirmation_date': format_date(imported_order['dataconferma'])}
        )
      continue

    with Session() as session:
      if product_service_user_handler(
        imported_order,
        result[0],
        result[1],
        create(
          Order,
          {
            'status': OrderStatus.NEW,
            'type': OrderType.DELIVERY,
            'cap': imported_order['CAP'],
            'external_status': external_status,
            'addressee': imported_order['cliente'],
            'external_id': imported_order['id_consegna'],
            'drc': format_date(imported_order['data_vendita']),
            'dpc': format_date(imported_order['data_consegna']),
            'addressee_contact': f'{imported_order["telefono"]} {imported_order["telefono1"]}',
            'customer_note': imported_order['note_conferma'] if imported_order['note_conferma'] != '' else None,
            'address': f'{imported_order["indirizzo"]} {imported_order["localita"]} {imported_order["provincia"]}',
            'confirmation_date': format_date(imported_order['dataconferma'])
            if imported_order['dataconferma'] != ''
            else None,
          },
          session=session,
        ),
        session,
      ):
        session.commit()
  return {'status': 'ok', 'message': 'Operazione commpletata'}


def update_order_status_by_euronics(status: int):
  if not EURONICS_API_PASSWORD:
    return {'status': 'ko', 'message': 'Api Key Error'}

  for imported_order in call_status_euronics_api(status):
    external_status = ORDER_STATUS_MAP[imported_order['stato']]
    order = get_order_by_external_id(imported_order['id_consegna'])
    if order and order.external_status != external_status:
      update(order, {'external_status': external_status})
  return {'status': 'ok', 'message': 'Operazione commpletata'}


def product_service_user_handler(
  imported_order: dict, user: User, collection_point: CollectionPoint, created_order: Order, session
):
  products = []
  service_users = []
  for item in imported_order['dettaglio']:
    service_user = get_service_user_by_user_and_code(user.id, item['cod_articolo'])
    if service_user:
      service_users.append(service_user)
    else:
      products.append({'name': item['descrizione'], 'services': []})

  if len(products) == 0:
    print('Nessun prodotto individuato')
    return False

  for product, service in zip(products, service_users):
    product['services'].append(service)
  remaining_services = service_users[len(products) :]
  for service in remaining_services:
    random.choice(products)['services'].append(service)

  for product in products:
    product_dict = {
      'name': product['name'],
      'order_id': created_order.id,
      'collection_point_id': collection_point.id,
    }
    if len(product['services']) == 0:
      product_dict['service_user_id'] = get_service_user_by_user_and_code(user.id, '777').id
      create(Product, product_dict, session=session)
    else:
      for service_user in product['services']:
        product_dict['service_user_id'] = (service_user.id,)
        create(Product, product_dict, session=session)
  return True


def format_date(date):
  return datetime.strptime(date, '%d/%m/%Y %H:%M:%S')


def call_list_euronics_api():
  return requests.get(
    'https://delivery.siemdistribuzione.it/Api/DeliveryVettoriAPI/ListaConsegne/',
    params={
      'user': 'cptrasporti',
      'pwd': EURONICS_API_PASSWORD
    }
  ).json()


def call_status_euronics_api(status: int):
  return requests.get(
    'https://delivery.siemdistribuzione.it/Api/DeliveryVettoriAPI/StatoConsegne/',
    params={
      'user': 'cptrasporti',
      'pwd': EURONICS_API_PASSWORD,
      'datain': (datetime.today() - timedelta(days=7)).strftime('%d/%m/%Y'),
      'dataout': (datetime.today() + timedelta(days=7)).strftime('%d/%m/%Y'),
      'stato': status
    }
  ).json()

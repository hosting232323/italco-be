import random
import requests

from database_api import Session
from ... import EURONICS_API_PASSWORD
from database_api.operations import create
from ...database.enum import OrderType, OrderStatus
from ..service.queries import get_service_user_by_user_and_code
from ..users.queries import get_user_and_collection_point_by_code
from ..orders.queries import get_order_by_external_id_and_customer
from ...database.schema import Order, Product, User, CollectionPoint


def save_orders_by_euronics():
  if not EURONICS_API_PASSWORD:
    return {'status': 'ko', 'message': 'Api Key Error'}

  for imported_order in call_euronics_api():
    result = get_user_and_collection_point_by_code(imported_order['cod_pv'])
    if not result or not result[0]:
      print(f'Non trovato punto vendita {imported_order["cod_pv"]}')
      continue

    if get_order_by_external_id_and_customer(imported_order['id_consegna'], result[0].id):
      print(f'Ordine già presente {imported_order["id_consegna"]}')
      continue

    with Session() as session:
      product_service_user_handler(
        imported_order,
        result[0],
        result[1],
        create(
          Order,
          {
            'type': OrderType.DELIVERY,
            'cap': imported_order['CAP'],
            'status': OrderStatus.NEW,
            'drc': imported_order['data_vendita'],
            'addressee': imported_order['cliente'],
            'dpc': imported_order['data_consegna'],
            'external_id': imported_order['id_consegna'],
            'addressee_contact': f'{imported_order["telefono"]} {imported_order["telefono1"]}',
            'address': f'{imported_order["indirizzo"]} {imported_order["localita"]} {imported_order["provincia"]}',
          },
          session=session,
        ),
        session,
      )

      session.commit()
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
    return

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


def call_euronics_api():
  return requests.get(
    f'https://delivery.siemdistribuzione.it/Api/DeliveryVettoriAPI/ListaConsegne/?user=cptrasporti&pwd={EURONICS_API_PASSWORD}'
  ).json()

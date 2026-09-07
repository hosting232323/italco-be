from ...database.enum import OrderType, RaeStatus
from ..rae.product import create_rae_product
from ...database.queries import is_rae_enabled
from .clone import format_data_cloning_product
from .queries import query_service_users, query_products
from database_api.operations import create, delete, get_by_id
from ...database.schema import Order, Product, RaeProduct, ServiceUser, Schedule
from ...order_integrity import InvalidOrderProductsError


def create_products(order: Order, products: dict, customer_user_id: int, cloned_order: bool, session):
  service_users = get_service_users(order, products, customer_user_id, session=session)
  for product in products.keys():
    create_product(product, products[product], order, service_users, session=session, cloned_order=cloned_order)


def update_products(
  order: Order,
  products: dict,
  customer_user_id: int,
  schedule: Schedule,
  session=None,
  order_type: OrderType = None,
):
  service_users = get_service_users(order, products, customer_user_id, session=session, order_type=order_type)
  old_products = query_products(order, session=session)

  for product in products.keys():
    if len([old_product for old_product in old_products if old_product.name == product]) > 0:
      continue

    create_product(product, products[product], order, service_users, session=session, schedule=schedule)

  for old_product in old_products:
    if old_product.name not in products:
      if old_product.rae_product_id:
        rae_product: RaeProduct = get_by_id(RaeProduct, old_product.rae_product_id, session=session)
        if rae_product and rae_product.status != RaeStatus.GENERATED:
          raise Exception(
            f"Impossibile eliminare il prodotto RAE '{old_product.name}': è eliminabile solo se in stato Generato."
          )
      delete(old_product, session=session)


def create_product(
  product_name: str,
  data: dict,
  order: Order,
  service_users: list[ServiceUser],
  session,
  schedule: Schedule = None,
  cloned_order=False,
):
  rae_product = None
  if 'rae_product' in data:
    # Unico punto in cui un ordine genera un prodotto RAE: ci passano creazione,
    # aggiornamento e clonazione. Il controllo sta qui e non sulle rotte /order
    # perché è il payload dei prodotti a portare il ritiro, non l'endpoint.
    if not is_rae_enabled():
      raise Exception('Il modulo RAEE non è attivo per questa attività: impossibile aggiungere un ritiro RAEE.')

    rae_product = create_rae_product(
      data['rae_product']['quantity'],
      data['rae_product']['rae_product_group_id'],
      order.id,
      service_users[0].user_id,
      session=session,
      schedule=schedule,
    )

  for service in data['services']:
    for service_user in service_users:
      if service_user.service_id == service['id']:
        product_data = {
          'order_id': order.id,
          'name': product_name,
          'service_user_id': service_user.id,
          'rae_product_id': rae_product.id if rae_product else None,
        }
        if cloned_order:
          product_data = format_data_cloning_product(product_data, data)
        elif 'collection_point' in data:
          product_data['collection_point_id'] = data['collection_point']['id']
        create(Product, product_data, session=session)
        break


def get_service_users(order: Order, products: dict, user_id: int, session=None, order_type: OrderType = None):
  if not isinstance(products, dict) or not products:
    raise InvalidOrderProductsError('Inserire almeno un prodotto con almeno un servizio.')

  service_ids = []
  for product_name, product in products.items():
    services = product.get('services') if isinstance(product, dict) else None
    if not isinstance(services, list) or not services:
      raise InvalidOrderProductsError(f'Il prodotto "{product_name}" deve avere almeno un servizio.')

    for service in services:
      service_id = service.get('id') if isinstance(service, dict) else None
      if not isinstance(service_id, int):
        raise InvalidOrderProductsError(f'Il prodotto "{product_name}" contiene un servizio non valido.')
      service_ids.append(service_id)

  # session=None esplicito non è passabile: db_session_decorator inietta il proprio
  # kwarg session mantenendo quelli originali, e i due collirebbero (TypeError).
  session_kwargs = {'session': session} if session is not None else {}
  service_users = query_service_users(
    list(set(service_ids)),
    user_id,
    order_type or order.type,
    **session_kwargs,
  )
  available_service_ids = {service_user.service_id for service_user in service_users}
  if set(service_ids) - available_service_ids:
    raise InvalidOrderProductsError(
      'Uno o più servizi selezionati non sono disponibili per il cliente o per il tipo di ordine.'
    )

  return service_users

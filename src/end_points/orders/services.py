from ...database.schema import Order, Product
from database_api.operations import create, delete
from .queries import query_service_users, query_products


def create_product(order: Order, products: dict, user_id: int, session=None):
  service_users = get_service_users(order, products, user_id)
  for product in products.keys():
    for service in products[product]['services']:
      for service_user in service_users:
        if service_user.service_id == service['id']:
          create(
            Product,
            {
              'name': product,
              'order_id': order.id,
              'service_user_id': service_user.id,
              'collection_point_id': products[product]['collection_point']['id'],
            },
            session=session,
          )
          break


def update_product(order: Order, products: dict, user_id: int, session=None):
  service_users = get_service_users(order, products, user_id)
  old_products = query_products(order)

  for product in products.keys():
    if len([old_product for old_product in old_products if old_product.name == product]) > 0:
      continue

    for service in products[product]['services']:
      for service_user in service_users:
        if service_user.service_id == service['id']:
          create(
            Product,
            {
              'name': product,
              'order_id': order.id,
              'service_user_id': service_user.id,
              'collection_point_id': products[product]['collection_point']['id'],
            },
            session=session,
          )
          break

  for old_product in old_products:
    if old_product.name not in products:
      delete(old_product, session=session)


def get_service_users(order: Order, products: dict, user_id: int):
  return query_service_users(
    list(set(service['id'] for product in products.values() for service in product['services'])), user_id, order.type
  )

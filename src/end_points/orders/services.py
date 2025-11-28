from database_api.operations import create, delete
from ...database.schema import Order, Product
from .queries import query_service_users, query_products


def create_product(order: Order, products: dict, user_id: int, session=None):
  service_users = query_service_users(
    list(set(service['id'] for services in products.values() for service in services)), user_id, order.type
  )
  for product in products.keys():
    for service in products[product]:
      for service_user in service_users:
        if service_user.service_id == service['id']:
          create(
            Product,
            {'order_id': order.id, 'service_user_id': service_user.id, 'product': product},
            session=session,
          )
          break


def update_product(order: Order, products: dict, user_id: int, session=None):
  service_users = query_service_users(
    list(set(service['id'] for services in products.values() for service in services)), user_id, order.type
  )
  products = query_products(order)

  for product in products.keys():
    if len([product for product in products if product.name == product]) > 0:
      continue

    for service in products[product]:
      for service_user in service_users:
        if service_user.service_id == service['id']:
          create(
            Product,
            {'order_id': order.id, 'service_user_id': service_user.id, 'product': product},
            session=session,
          )
          break

  for product in list({product.name for product in products}):
    for product in [product for product in products if product.name == product]:
      if product.name not in products:
        delete(product, session=session)

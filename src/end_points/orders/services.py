from database_api.operations import create, delete
from ...database.schema import Order, OrderServiceUser
from .queries import query_service_users, query_order_service_users


def create_order_service_user(order: Order, products: dict, user_id: int):
  service_users = query_service_users(
    list(set(service['id'] for services in products.values() for service in services)),
    user_id,
    order.type
  )
  for product in products.keys():
    for service in products[product]:
      for service_user in service_users:
        if service_user.service_id == service['id']:
          create(OrderServiceUser, {
            'order_id': order.id,
            'service_user_id': service_user.id,
            'product': product
          })
          break


def update_order_service_user(order: Order, products: dict, user_id: int):
  service_users = query_service_users(
    list(set(service['id'] for services in products.values() for service in services)),
    user_id,
    order.type
  )
  order_service_users = query_order_service_users(order)

  for product in products.keys():
    if len([
      order_service_user for order_service_user in order_service_users if order_service_user.product == product
    ]) > 0:
      continue

    for service in products[product]:
      for service_user in service_users:
        if service_user.service_id == service['id']:
          create(OrderServiceUser, {
            'order_id': order.id,
            'service_user_id': service_user.id,
            'product': product
          })
          break

  for product in list({
    order_service_user.product for order_service_user in order_service_users
  }):
    for order_service_user in [
      order_service_user for order_service_user in order_service_users if order_service_user.product == product
    ]:
      if not order_service_user.product in products:
        delete(order_service_user)

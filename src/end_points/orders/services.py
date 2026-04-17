from database_api.operations import create, delete
from .queries import query_service_users, query_products
from ...database.schema import Order, Product, RaeProduct, ServiceUser


def create_products(order: Order, products: dict, user_id: int, session=None):
  service_users = get_service_users(order, products, user_id)
  for product in products.keys():
    create_product(product, products[product], order, service_users, session=session)


def update_products(order: Order, products: dict, user_id: int, session=None):
  service_users = get_service_users(order, products, user_id)
  old_products = query_products(order)

  for product in products.keys():
    if len([old_product for old_product in old_products if old_product.name == product]) > 0:
      continue

    create_product(product, products[product], order, service_users, session=session)

  for old_product in old_products:
    if old_product.name not in products:
      delete(old_product, session=session)


def create_product(product_name: str, data: dict, order: Order, service_users: list[ServiceUser], session):
  rae_product = None
  if 'rae_product' in data:
    rae_product: RaeProduct = create(
      RaeProduct,
      {
        'user_id': service_users[0].user_id,
        'quantity': data['rae_product']['quantity'],
        'rae_product_group_id': data['rae_product']['rae_product_group_id'],
      },
      session=session,
    )

  for service in data['services']:
    for service_user in service_users:
      if service_user.service_id == service['id']:
        create(
          Product,
          {
            'order_id': order.id,
            'name': product_name,
            'service_user_id': service_user.id,
            'collection_point_id': data['collection_point']['id'],
            'rae_product_id': rae_product.id if rae_product else None,
          },
          session=session,
        )
        break


def get_service_users(order: Order, products: dict, user_id: int):
  return query_service_users(
    list(set(service['id'] for product in products.values() for service in product['services'])), user_id, order.type
  )

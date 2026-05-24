import os
from sqlalchemy import text
from flask import send_from_directory
from sqlalchemy.orm import Session as session_type

from api.storage import upload_file
from .clone import format_data_cloning_product
from database_api.operations import create, delete
from ... import STATIC_FOLDER, IS_DEV, get_base_path
from .queries import query_service_users, query_products
from ...database.schema import Order, Product, RaeProduct, ServiceUser


def create_products(order: Order, products: dict, customer_user_id: int, cloned_order: bool, session):
  service_users = get_service_users(order, products, customer_user_id)
  for product in products.keys():
    create_product(product, products[product], order, service_users, session=session, cloned_order=cloned_order)


def update_products(order: Order, products: dict, customer_user_id: int, session=None):
  service_users = get_service_users(order, products, customer_user_id)
  old_products = query_products(order)

  for product in products.keys():
    if len([old_product for old_product in old_products if old_product.name == product]) > 0:
      continue

    create_product(product, products[product], order, service_users, session=session)

  for old_product in old_products:
    if old_product.name not in products:
      delete(old_product, session=session)


def create_product(
  product_name: str, data: dict, order: Order, service_users: list[ServiceUser], session, cloned_order=False
):
  rae_product = None
  if 'rae_product' in data:
    id = guess_next_id(session)
    rae_product: RaeProduct = create(
      RaeProduct,
      {
        'user_id': service_users[0].user_id,
        'quantity': data['rae_product']['quantity'],
        'rae_product_group_id': data['rae_product']['rae_product_group_id'],
        'link': get_base_path('rae-product/document')
          + os.path.basename(
          upload_file(
            'uploaded_file',
            f'{id}.pdf',
            os.path.join(STATIC_FOLDER, 'rae-product'),
            'local',
          )
        )
      },
      session=session,
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
        else:
          product_data['collection_point_id'] = data['collection_point']['id']
        create(Product, product_data, session=session)
        break


def serve_document(filename: str):
  return send_from_directory(
    os.path.join(STATIC_FOLDER, 'rae-product', 'test' if IS_DEV else 'prod'),
    filename,
  )


def get_service_users(order: Order, products: dict, user_id: int):
  return query_service_users(
    list(set(service['id'] for product in products.values() for service in product['services'])), user_id, order.type
  )


def guess_next_id(session: session_type) -> int:
  return session.execute(text("SELECT nextval('rae_product_id_seq')")).scalar()

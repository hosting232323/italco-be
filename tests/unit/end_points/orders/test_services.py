import pytest

from database_api import Session
from database_api.operations import create

from src.database.enum import RaeStatus
from src.database.schema import Product, RaeProduct
from src.end_points.orders.services import create_products, get_service_users, update_products

from tests.unit.factories import (
  create_order,
  create_product,
  create_rae_product_group,
  customer_with_service,
)


def _products_payload(service, collection_point, name='Lavatrice', **extra):
  return {name: {'services': [{'id': service.id}], 'collection_point': {'id': collection_point.id}, **extra}}


def test_create_products_links_service_user_and_collection_point(db):
  customer, service, service_user, collection_point = customer_with_service()
  order = create_order()

  with Session() as session:
    create_products(order, _products_payload(service, collection_point), customer.id, False, session=session)
    session.commit()

  with Session() as session:
    product = session.query(Product).one()
    assert product.service_user_id == service_user.id
    assert product.collection_point_id == collection_point.id


def test_create_products_with_rae_product(db):
  customer, service, _, collection_point = customer_with_service()
  group = create_rae_product_group()
  order = create_order()
  payload = _products_payload(
    service,
    collection_point,
    rae_product={'quantity': 3, 'rae_product_group_id': group.id},
  )

  with Session() as session:
    create_products(order, payload, customer.id, False, session=session)
    session.commit()

  with Session() as session:
    rae_product = session.query(RaeProduct).one()
    assert rae_product.quantity == 3
    assert rae_product.status == RaeStatus.GENERATED
    assert session.query(Product).one().rae_product_id == rae_product.id


def test_update_products_keeps_existing_and_adds_new(db):
  customer, service, service_user, collection_point = customer_with_service()
  order = create_order()
  create_product(order, service_user, name='Esistente')

  payload = {
    'Esistente': {'services': [{'id': service.id}], 'collection_point': {'id': collection_point.id}},
    'Nuovo': {'services': [{'id': service.id}], 'collection_point': {'id': collection_point.id}},
  }
  with Session() as session:
    update_products(order, payload, customer.id, None, session=session)
    session.commit()

  with Session() as session:
    names = {product.name for product in session.query(Product).all()}
    assert names == {'Esistente', 'Nuovo'}


def test_update_products_removes_missing_products(db):
  customer, service, service_user, collection_point = customer_with_service()
  order = create_order()
  create_product(order, service_user, name='DaRimuovere')

  with Session() as session:
    update_products(
      order, _products_payload(service, collection_point, name='Rimasto'), customer.id, None, session=session
    )
    session.commit()

  with Session() as session:
    assert [product.name for product in session.query(Product).all()] == ['Rimasto']


def test_update_products_blocks_deletion_of_emitted_rae(db):
  customer, service, service_user, collection_point = customer_with_service()
  group = create_rae_product_group()
  order = create_order()
  rae_product = create(
    RaeProduct,
    {
      'order_id': order.id,
      'user_id': customer.id,
      'rae_product_group_id': group.id,
      'status': RaeStatus.EMITTED,
    },
  )
  create_product(order, service_user, name='ConRae', rae_product_id=rae_product.id)

  with pytest.raises(Exception, match='solo se in stato Generato'):
    with Session() as session:
      update_products(
        order, _products_payload(service, collection_point, name='Altro'), customer.id, None, session=session
      )
      session.commit()


def test_update_products_allows_deletion_of_generated_rae(db):
  customer, service, service_user, collection_point = customer_with_service()
  group = create_rae_product_group()
  order = create_order()
  rae_product = create(
    RaeProduct,
    {
      'order_id': order.id,
      'user_id': customer.id,
      'rae_product_group_id': group.id,
      'status': RaeStatus.GENERATED,
    },
  )
  create_product(order, service_user, name='ConRae', rae_product_id=rae_product.id)

  with Session() as session:
    update_products(
      order, _products_payload(service, collection_point, name='Sostituto'), customer.id, None, session=session
    )
    session.commit()

  with Session() as session:
    assert [product.name for product in session.query(Product).all()] == ['Sostituto']


def test_get_service_users_deduplicates_service_ids(db):
  customer, service, service_user, collection_point = customer_with_service()
  order = create_order()
  products = {
    'A': {'services': [{'id': service.id}], 'collection_point': {'id': collection_point.id}},
    'B': {'services': [{'id': service.id}], 'collection_point': {'id': collection_point.id}},
  }

  results = get_service_users(order, products, customer.id)

  assert [su.id for su in results] == [service_user.id]

from database_api.operations import get_by_id

from src.database.enum import UserRole
from src.database.schema import CollectionPoint
from src.end_points.collection_point import query_collection_points, query_collection_points_available

from tests.unit.factories import (
  auth_header,
  create_collection_point,
  create_order,
  create_product,
  create_user,
  customer_with_service,
)


def test_create_collection_point_binds_to_authenticated_customer(client):
  customer = create_user(UserRole.CUSTOMER)

  response = client.post(
    '/collection-point',
    json={'name': 'Magazzino', 'address': 'Via X 1', 'cap': '70020'},
    headers=auth_header(customer),
  )

  body = response.get_json()
  assert body['status'] == 'ok'
  assert body['collection_point']['user_id'] == customer.id


def test_get_collection_points_customer_sees_only_own(client):
  customer = create_user(UserRole.CUSTOMER)
  own = create_collection_point(customer)
  other_customer = create_user(UserRole.CUSTOMER)
  create_collection_point(other_customer)

  response = client.get('/collection-point', headers=auth_header(customer))

  body = response.get_json()
  assert [cp['id'] for cp in body['collection_points']] == [own.id]


def test_get_collection_points_admin_sees_all(client):
  admin = create_user(UserRole.ADMIN)
  customer = create_user(UserRole.CUSTOMER)
  create_collection_point(customer)
  create_collection_point(customer)

  response = client.get('/collection-point', headers=auth_header(admin))

  assert len(response.get_json()['collection_points']) == 2


def test_update_collection_point(client):
  customer = create_user(UserRole.CUSTOMER)
  collection_point = create_collection_point(customer)

  response = client.put(
    f'/collection-point/{collection_point.id}', json={'name': 'Nuovo nome'}, headers=auth_header(customer)
  )

  assert response.get_json()['status'] == 'ok'
  assert get_by_id(CollectionPoint, collection_point.id).name == 'Nuovo nome'


def test_delete_collection_point(client):
  customer = create_user(UserRole.CUSTOMER)
  collection_point = create_collection_point(customer)

  response = client.delete(f'/collection-point/{collection_point.id}', headers=auth_header(customer))

  assert response.get_json()['status'] == 'ok'
  assert get_by_id(CollectionPoint, collection_point.id) is None


def test_query_collection_points_available_follows_order_products(db):
  _, _, service_user, collection_point = customer_with_service()
  order = create_order()
  create_product(order, service_user)
  # punto di ritiro di un altro cliente, non collegato all'ordine
  create_collection_point(create_user(UserRole.CUSTOMER))

  available = query_collection_points_available(order.id)

  assert [cp.id for cp in available] == [collection_point.id]


def test_query_collection_points_respects_role(db):
  customer = create_user(UserRole.CUSTOMER)
  own = create_collection_point(customer)
  admin = create_user(UserRole.ADMIN)
  other = create_collection_point(create_user(UserRole.CUSTOMER))

  assert [cp.id for cp in query_collection_points(customer)] == [own.id]
  assert {cp.id for cp in query_collection_points(admin)} == {own.id, other.id}

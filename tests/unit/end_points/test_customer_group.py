from database_api.operations import create, get_by_id, update

from src.database.enum import UserRole
from src.database.schema import CustomerGroup, User
from src.end_points.customer_group import format_query_result, query_customer_groups

from tests.unit.factories import auth_header, create_user


def test_create_customer_group(client):
  admin = create_user(UserRole.ADMIN)

  response = client.post('/customer-group', json={'name': 'GDO Nord'}, headers=auth_header(admin))

  body = response.get_json()
  assert body['status'] == 'ok'
  assert body['customer_group']['name'] == 'GDO Nord'


def test_assign_customer_group_to_user(client):
  admin = create_user(UserRole.ADMIN)
  customer = create_user(UserRole.CUSTOMER)
  group = create(CustomerGroup, {'name': 'Gruppo A'})

  response = client.put(
    '/customer-group/user',
    json={'user_id': customer.id, 'customer_group_id': group.id},
    headers=auth_header(admin),
  )

  assert response.get_json()['status'] == 'ok'
  assert get_by_id(User, customer.id).customer_group_id == group.id


def test_delete_customer_group(client):
  admin = create_user(UserRole.ADMIN)
  group = create(CustomerGroup, {'name': 'Da cancellare'})

  response = client.delete(f'/customer-group/{group.id}', headers=auth_header(admin))

  assert response.get_json()['status'] == 'ok'
  assert get_by_id(CustomerGroup, group.id) is None


def test_get_customer_groups_aggregates_users(client):
  admin = create_user(UserRole.ADMIN)
  group = create(CustomerGroup, {'name': 'Con utenti'})
  empty_group = create(CustomerGroup, {'name': 'Vuoto'})
  first = create_user(UserRole.CUSTOMER)
  second = create_user(UserRole.CUSTOMER)
  update(first, {'customer_group_id': group.id})
  update(second, {'customer_group_id': group.id})

  response = client.get('/customer-group', headers=auth_header(admin))

  body = response.get_json()
  assert body['status'] == 'ok'
  by_id = {entry['id']: entry for entry in body['customer_groups']}
  assert {user['id'] for user in by_id[group.id]['users']} == {first.id, second.id}
  assert by_id[empty_group.id]['users'] == []


def test_get_customer_groups_visible_to_customer_role(client):
  customer = create_user(UserRole.CUSTOMER)
  create(CustomerGroup, {'name': 'Visibile'})

  response = client.get('/customer-group', headers=auth_header(customer))

  assert response.get_json()['status'] == 'ok'


def test_query_and_format_helpers(db):
  group = create(CustomerGroup, {'name': 'Helper'})
  customer = create_user(UserRole.CUSTOMER)
  update(customer, {'customer_group_id': group.id})

  results = []
  for tupla in query_customer_groups():
    results = format_query_result(tupla, results)

  assert len(results) == 1
  assert results[0]['users'][0]['id'] == customer.id

import pytest
from database_api.operations import get_by_id

from src.database.enum import OrderType, UserRole
from src.database.schema import Service, ServiceUser
from src.end_points.service import service_bp  # noqa: F401 - importato per coerenza col modulo testato

from tests.unit.factories import (
  auth_header,
  create_service,
  create_service_user,
  create_user,
)


def test_create_service(client):
  admin = create_user(UserRole.ADMIN)

  response = client.post(
    '/service',
    json={'name': 'Montaggio', 'type': 'Delivery', 'duration': 30},
    headers=auth_header(admin),
  )

  body = response.get_json()
  assert body['status'] == 'ok'
  assert body['service']['type'] == 'Delivery'
  assert get_by_id(Service, body['service']['id']).type == OrderType.DELIVERY


def test_get_services_aggregates_users(client):
  admin = create_user(UserRole.ADMIN)
  service = create_service()
  first = create_user(UserRole.CUSTOMER)
  second = create_user(UserRole.CUSTOMER)
  create_service_user(first, service)
  create_service_user(second, service)

  response = client.get('/service', headers=auth_header(admin))

  body = response.get_json()
  assert body['status'] == 'ok'
  assert len(body['services']) == 1
  assert {user['user_id'] for user in body['services'][0]['users']} == {first.id, second.id}
  assert all('nickname' in user for user in body['services'][0]['users'])


def test_get_services_customer_sees_only_associated(client):
  customer = create_user(UserRole.CUSTOMER)
  associated = create_service()
  create_service_user(customer, associated)
  create_service()  # servizio non associato

  response = client.get('/service', headers=auth_header(customer))

  body = response.get_json()
  assert [service['id'] for service in body['services']] == [associated.id]


def test_update_service(client):
  admin = create_user(UserRole.ADMIN)
  service = create_service(OrderType.DELIVERY)

  response = client.put(
    f'/service/{service.id}', json={'name': 'Nuovo nome', 'type': 'Check'}, headers=auth_header(admin)
  )

  assert response.get_json()['status'] == 'ok'
  refreshed = get_by_id(Service, service.id)
  assert refreshed.name == 'Nuovo nome'
  assert refreshed.type == OrderType.CHECK


def test_delete_service(client):
  admin = create_user(UserRole.ADMIN)
  service = create_service()

  response = client.delete(f'/service/{service.id}', headers=auth_header(admin))

  assert response.get_json()['status'] == 'ok'
  assert get_by_id(Service, service.id) is None


def test_create_service_user(client):
  admin = create_user(UserRole.ADMIN)
  customer = create_user(UserRole.CUSTOMER)
  service = create_service()

  response = client.post(
    '/service/customer',
    json={'user_id': customer.id, 'service_id': service.id, 'price': 12.5},
    headers=auth_header(admin),
  )

  body = response.get_json()
  assert body['status'] == 'ok'
  assert body['service_user']['nickname'] == customer.nickname
  assert body['service_user']['price'] == 12.5


def test_create_service_user_rejects_duplicates(client):
  admin = create_user(UserRole.ADMIN)
  customer = create_user(UserRole.CUSTOMER)
  service = create_service()
  create_service_user(customer, service)

  response = client.post(
    '/service/customer',
    json={'user_id': customer.id, 'service_id': service.id, 'price': 12.5},
    headers=auth_header(admin),
  )

  assert response.get_json()['status'] == 'ko'


def test_update_service_user(client):
  admin = create_user(UserRole.ADMIN)
  customer = create_user(UserRole.CUSTOMER)
  service_user = create_service_user(customer, create_service())

  response = client.put(f'/service/customer/{service_user.id}', json={'price': 99.0}, headers=auth_header(admin))

  assert response.get_json()['status'] == 'ok'
  assert get_by_id(ServiceUser, service_user.id).price == 99.0


def test_delete_service_user(client):
  admin = create_user(UserRole.ADMIN)
  customer = create_user(UserRole.CUSTOMER)
  service_user = create_service_user(customer, create_service())

  response = client.delete(f'/service/customer/{service_user.id}', headers=auth_header(admin))

  assert response.get_json()['status'] == 'ok'
  assert get_by_id(ServiceUser, service_user.id) is None


def test_set_all_users_associates_customers_without_the_service(client):
  admin = create_user(UserRole.ADMIN)
  service = create_service()
  missing = create_user(UserRole.CUSTOMER)

  response = client.get(f'/service/set-all-users?service_id={service.id}&price=20', headers=auth_header(admin))

  body = response.get_json()
  assert body['status'] == 'ok'
  assert [entry['user_id'] for entry in body['service_users']] == [missing.id]
  assert body['service_users'][0]['price'] == 20.0


@pytest.mark.xfail(
  strict=True,
  reason=(
    'Bug sorgente: set_all_users confronta User.id con la lista degli ID di ServiceUser '
    '(query_service_user restituisce ServiceUser, non user_id), quindi i clienti già '
    'associati al servizio non vengono esclusi e ricevono un ServiceUser duplicato.'
  ),
)
def test_set_all_users_should_skip_already_associated_customers(client):
  admin = create_user(UserRole.ADMIN)
  service = create_service()
  already = create_user(UserRole.CUSTOMER)
  create_service_user(already, service, price=5.0)
  missing = create_user(UserRole.CUSTOMER)

  response = client.get(f'/service/set-all-users?service_id={service.id}&price=20', headers=auth_header(admin))

  body = response.get_json()
  # Comportamento corretto atteso: solo il cliente senza il servizio viene associato
  assert [entry['user_id'] for entry in body['service_users']] == [missing.id]

from database_api.operations import get_by_id

from src.database.enum import UserRole
from src.database.schema import Transport
from src.end_points.transport import query_transports

from tests.unit.factories import (
  auth_header,
  create_transport,
  create_user,
)


def test_create_transport(client):
  admin = create_user(UserRole.ADMIN)

  response = client.post(
    '/transport', json={'name': 'Furgone 1', 'plate': 'AA123BB', 'cap': '70020'}, headers=auth_header(admin)
  )

  body = response.get_json()
  assert body['status'] == 'ok'
  assert body['transport']['plate'] == 'AA123BB'
  assert get_by_id(Transport, body['transport']['id']) is not None


def test_get_transports_as_operator(client):
  operator = create_user(UserRole.OPERATOR)
  create_transport()
  create_transport()

  response = client.get('/transport', headers=auth_header(operator))

  body = response.get_json()
  assert body['status'] == 'ok'
  assert len(body['transports']) == 2


def test_update_transport(client):
  admin = create_user(UserRole.ADMIN)
  transport = create_transport()

  response = client.put(f'/transport/{transport.id}', json={'name': 'Rinominato'}, headers=auth_header(admin))

  assert response.get_json()['status'] == 'ok'
  assert get_by_id(Transport, transport.id).name == 'Rinominato'


def test_delete_transport(client):
  admin = create_user(UserRole.ADMIN)
  transport = create_transport()

  response = client.delete(f'/transport/{transport.id}', headers=auth_header(admin))

  assert response.get_json()['status'] == 'ok'
  assert get_by_id(Transport, transport.id) is None


def test_transport_endpoints_require_admin(client):
  delivery = create_user(UserRole.DELIVERY)

  response = client.post('/transport', json={'name': 'x', 'plate': 'y'}, headers=auth_header(delivery))

  assert response.status_code == 403
  assert response.get_json()['status'] == 'forbidden'


def test_query_transports(db):
  transports = [create_transport(), create_transport()]

  assert {t.id for t in query_transports()} == {t.id for t in transports}

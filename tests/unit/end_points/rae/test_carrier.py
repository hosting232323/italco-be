from database_api.operations import get_by_id

from src.database.enum import UserRole
from src.database.schema import Carrier

from tests.unit.factories import auth_header, create_carrier, create_user


def test_create_carrier(client):
  admin = create_user(UserRole.ADMIN)

  response = client.post(
    '/rae/carrier',
    json={'company_name': 'Trasporti SpA', 'vat_number': 'IT123'},
    headers=auth_header(admin),
  )

  assert response.get_json()['status'] == 'ok'


def test_get_carriers(client):
  operator = create_user(UserRole.OPERATOR)
  create_carrier()
  create_carrier()

  response = client.get('/rae/carrier', headers=auth_header(operator))

  body = response.get_json()
  assert body['status'] == 'ok'
  assert len(body['rae_carriers']) == 2


def test_update_carrier(client):
  admin = create_user(UserRole.ADMIN)
  carrier = create_carrier()

  response = client.put(
    f'/rae/carrier/{carrier.id}', json={'company_name': 'Rinominata'}, headers=auth_header(admin)
  )

  assert response.get_json()['status'] == 'ok'
  assert get_by_id(Carrier, carrier.id).company_name == 'Rinominata'


def test_delete_carrier(client):
  admin = create_user(UserRole.ADMIN)
  carrier = create_carrier()

  response = client.delete(f'/rae/carrier/{carrier.id}', headers=auth_header(admin))

  assert response.get_json()['status'] == 'ok'
  assert get_by_id(Carrier, carrier.id) is None

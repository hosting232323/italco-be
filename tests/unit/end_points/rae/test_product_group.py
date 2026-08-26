from database_api.operations import get_by_id

from src.database.enum import UserRole
from src.database.schema import RaeProductGroup

from tests.unit.factories import auth_header, create_rae_product_group, create_user


def test_create_product_group(client):
  admin = create_user(UserRole.ADMIN)

  response = client.post(
    '/rae/product-group',
    json={'name': 'Frigoriferi', 'cer_code': 200123, 'group_code': 'R1'},
    headers=auth_header(admin),
  )

  body = response.get_json()
  assert body['status'] == 'ok'
  assert body['rae_product']['group_code'] == 'R1'


def test_get_product_groups(client):
  operator = create_user(UserRole.OPERATOR)
  create_rae_product_group()
  create_rae_product_group()

  response = client.get('/rae/product-group', headers=auth_header(operator))

  body = response.get_json()
  assert body['status'] == 'ok'
  assert len(body['rae_product_groups']) == 2


def test_update_product_group(client):
  admin = create_user(UserRole.ADMIN)
  group = create_rae_product_group()

  response = client.put(f'/rae/product-group/{group.id}', json={'name': 'Aggiornato'}, headers=auth_header(admin))

  assert response.get_json()['status'] == 'ok'
  assert get_by_id(RaeProductGroup, group.id).name == 'Aggiornato'


def test_delete_product_group(client):
  admin = create_user(UserRole.ADMIN)
  group = create_rae_product_group()

  response = client.delete(f'/rae/product-group/{group.id}', headers=auth_header(admin))

  assert response.get_json()['status'] == 'ok'
  assert get_by_id(RaeProductGroup, group.id) is None


def test_product_group_requires_admin_for_writes(client):
  operator = create_user(UserRole.OPERATOR)

  response = client.post(
    '/rae/product-group', json={'name': 'x', 'cer_code': 1, 'group_code': 'R9'}, headers=auth_header(operator)
  )

  assert response.status_code == 403
  assert response.get_json()['status'] == 'forbidden'

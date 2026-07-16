from database_api.operations import get_by_id

from src.database.enum import UserRole
from src.database.schema import CollectionCenter

from tests.unit.factories import auth_header, create_collection_center, create_user


def test_create_collection_center(client):
  admin = create_user(UserRole.ADMIN)

  response = client.post(
    '/rae/collection-center',
    json={'company_name': 'Centro Raccolta Bari'},
    headers=auth_header(admin),
  )

  assert response.get_json()['status'] == 'ok'


def test_get_collection_centers(client):
  operator = create_user(UserRole.OPERATOR)
  create_collection_center()

  response = client.get('/rae/collection-center', headers=auth_header(operator))

  body = response.get_json()
  assert body['status'] == 'ok'
  assert len(body['rae_collection_centers']) == 1


def test_update_collection_center(client):
  admin = create_user(UserRole.ADMIN)
  center = create_collection_center()

  response = client.put(
    f'/rae/collection-center/{center.id}', json={'address': 'Via Nuova 1'}, headers=auth_header(admin)
  )

  assert response.get_json()['status'] == 'ok'
  assert get_by_id(CollectionCenter, center.id).address == 'Via Nuova 1'


def test_delete_collection_center(client):
  admin = create_user(UserRole.ADMIN)
  center = create_collection_center()

  response = client.delete(f'/rae/collection-center/{center.id}', headers=auth_header(admin))

  assert response.get_json()['status'] == 'ok'
  assert get_by_id(CollectionCenter, center.id) is None

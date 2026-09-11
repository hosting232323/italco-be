from database_api import Session
from database_api.operations import get_by_id

from src.database.enum import UserRole
from src.database.schema import Transport, DeliveryUserInfo
from src.end_points.transport import query_transports, sync_transport_users

from tests.unit.factories import (
  auth_header,
  create_delivery_info,
  create_transport,
  create_user,
)


def _info_for(user):
  with Session() as session:
    return session.query(DeliveryUserInfo).filter(DeliveryUserInfo.user_id == user.id).first()


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


def test_create_transport_links_delivery_users(client):
  admin = create_user(UserRole.ADMIN)
  first = create_user(UserRole.DELIVERY)
  second = create_user(UserRole.DELIVERY)
  create_delivery_info(first, cap='70020')

  response = client.post(
    '/transport',
    json={'name': 'Furgone', 'plate': 'AA111BB', 'user_ids': [first.id, second.id]},
    headers=auth_header(admin),
  )

  body = response.get_json()
  assert body['status'] == 'ok'
  assert sorted(body['transport']['user_ids']) == sorted([first.id, second.id])
  # La riga info mancante viene creata al volo per poter reggere la FK.
  assert _info_for(first).transport_id == body['transport']['id']
  assert _info_for(second).transport_id == body['transport']['id']


def test_update_transport_reconciles_user_list(client):
  admin = create_user(UserRole.ADMIN)
  kept = create_user(UserRole.DELIVERY)
  dropped = create_user(UserRole.DELIVERY)
  transport = create_transport()
  create_delivery_info(kept, transport_id=transport.id)
  create_delivery_info(dropped, transport_id=transport.id)

  response = client.put(
    f'/transport/{transport.id}',
    json={'name': transport.name, 'plate': transport.plate, 'user_ids': [kept.id]},
    headers=auth_header(admin),
  )

  assert response.get_json()['status'] == 'ok'
  assert _info_for(kept).transport_id == transport.id
  assert _info_for(dropped).transport_id is None


def test_update_transport_moves_user_from_another_vehicle(client):
  admin = create_user(UserRole.ADMIN)
  user = create_user(UserRole.DELIVERY)
  old = create_transport()
  new = create_transport()
  create_delivery_info(user, transport_id=old.id)

  client.put(
    f'/transport/{new.id}',
    json={'name': new.name, 'plate': new.plate, 'user_ids': [user.id]},
    headers=auth_header(admin),
  )

  assert _info_for(user).transport_id == new.id


def test_update_transport_without_user_ids_keeps_links(client):
  admin = create_user(UserRole.ADMIN)
  user = create_user(UserRole.DELIVERY)
  transport = create_transport()
  create_delivery_info(user, transport_id=transport.id)

  client.put(f'/transport/{transport.id}', json={'name': 'Rinominato'}, headers=auth_header(admin))

  assert _info_for(user).transport_id == transport.id


def test_get_transports_exposes_assigned_users(client):
  admin = create_user(UserRole.ADMIN)
  user = create_user(UserRole.DELIVERY, nickname='mario')
  transport = create_transport()
  create_delivery_info(user, transport_id=transport.id)

  response = client.get('/transport', headers=auth_header(admin))

  entry = next(t for t in response.get_json()['transports'] if t['id'] == transport.id)
  assert entry['user_ids'] == [user.id]
  assert entry['delivery_users'] == [{'id': user.id, 'nickname': 'mario'}]


def test_delete_transport_detaches_users(client):
  admin = create_user(UserRole.ADMIN)
  user = create_user(UserRole.DELIVERY)
  transport = create_transport()
  create_delivery_info(user, transport_id=transport.id)

  client.delete(f'/transport/{transport.id}', headers=auth_header(admin))

  assert _info_for(user).transport_id is None


def test_sync_transport_users_is_idempotent(db):
  user = create_user(UserRole.DELIVERY)
  transport = create_transport()
  create_delivery_info(user)

  sync_transport_users(transport.id, [user.id])
  sync_transport_users(transport.id, [user.id])

  with Session() as session:
    rows = session.query(DeliveryUserInfo).filter(DeliveryUserInfo.user_id == user.id).all()
  assert len(rows) == 1
  assert rows[0].transport_id == transport.id

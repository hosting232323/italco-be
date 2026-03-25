from uuid import uuid4

from database_api import Session
from database_api.operations import get_by_id

import src.end_points.users as users_endpoints
from src.database.enum import UserRole
from src.database.schema import CustomerUserInfo, DeliveryUserInfo, User
from tests.utils import auth_header_for, create_user_for_login


def _uniq(prefix: str) -> str:
  return f'{prefix}.{uuid4().hex[:8]}@example.com'


def test_get_users_returns_seeded_users(client):
  response = client.get('/users/', headers=auth_header_for('admin', role=UserRole.ADMIN))

  assert response.status_code == 200
  body = response.get_json()
  assert body['status'] == 'ok'
  assert len(body['users']) >= 4
  assert 'new_token' in body


def test_create_user_creates_when_nickname_available(client):
  nickname = _uniq('new.user')
  response = client.post(
    '/users/',
    json={'nickname': nickname, 'password': 'pw', 'role': 'Delivery'},
    headers=auth_header_for('admin', role=UserRole.ADMIN),
  )

  assert response.status_code == 200
  assert response.get_json()['status'] == 'ok'

  with Session() as session:
    created = session.query(User).filter(User.nickname == nickname).first()
    assert created is not None
    assert created.role == UserRole.DELIVERY


def test_create_user_rejects_duplicate_nickname(client):
  duplicate_nickname = _uniq('dup.user')
  create_user_for_login(duplicate_nickname, 'pw', UserRole.DELIVERY)
  response = client.post(
    '/users/',
    json={'nickname': duplicate_nickname, 'password': 'pw', 'role': 'Delivery'},
    headers=auth_header_for('admin', role=UserRole.ADMIN),
  )

  assert response.status_code == 200
  assert response.get_json()['status'] == 'ko'


def test_delete_user_without_force_returns_dependencies(client):
  user = create_user_for_login(_uniq('delete.target'), 'pw', UserRole.CUSTOMER)
  response = client.delete(f'/users/{user.id}', headers=auth_header_for('admin', role=UserRole.ADMIN))

  assert response.status_code == 200
  body = response.get_json()
  assert body['status'] == 'ko'
  assert 'dependencies' in body


def test_delete_user_with_force_deletes_user(client):
  temp_user = create_user_for_login(_uniq('delete.me'), 'pw', UserRole.CUSTOMER)

  response = client.delete(
    f'/users/{temp_user.id}?force=1',
    headers=auth_header_for('admin', role=UserRole.ADMIN),
  )

  assert response.status_code == 200
  assert response.get_json()['status'] == 'ok'
  assert get_by_id(User, temp_user.id) is None


def test_login_returns_token_for_valid_credentials(client):
  nickname = _uniq('login.user')
  create_user_for_login(nickname, 'pw', UserRole.DELIVERY)

  response = client.post('/users/login', json={'email': nickname, 'password': 'pw'})

  assert response.status_code == 200
  body = response.get_json()
  assert body['status'] == 'ok'
  assert body['role'] == 'Delivery'
  assert 'token' in body


def test_login_returns_error_for_unknown_user(client):
  response = client.post('/users/login', json={'email': 'missing@example.com', 'password': 'pw'})

  assert response.status_code == 200
  assert response.get_json()['status'] == 'ko'


def test_update_position_creates_delivery_info(client):
  delivery_user = create_user_for_login(_uniq('delivery.pos'), 'pw', UserRole.DELIVERY)
  response = client.post(
    '/users/position',
    json={'lat': '45.123', 'lon': '9.456'},
    headers=auth_header_for(delivery_user.nickname, role=UserRole.DELIVERY),
  )

  assert response.status_code == 200
  assert response.get_json()['status'] == 'ok'

  with Session() as session:
    info = session.query(DeliveryUserInfo).filter(DeliveryUserInfo.user_id == delivery_user.id).first()
    assert info is not None
    assert float(info.lat) == 45.123
    assert float(info.lon) == 9.456


def test_save_user_info_endpoint_updates_delivery_data(client):
  delivery_user = create_user_for_login(_uniq('delivery.info'), 'pw', UserRole.DELIVERY)
  response = client.post(
    '/users/info',
    json={'user_id': delivery_user.id, 'class': 'Delivery', 'data': {'cap': '70020'}},
    headers=auth_header_for('admin', role=UserRole.ADMIN),
  )

  assert response.status_code == 200
  assert response.get_json()['status'] == 'ok'

  with Session() as session:
    info = session.query(DeliveryUserInfo).filter(DeliveryUserInfo.user_id == delivery_user.id).first()
    assert info is not None
    assert info.cap == '70020'


def test_save_user_info_endpoint_updates_customer_data(client):
  customer_user = create_user_for_login(_uniq('customer.info'), 'pw', UserRole.CUSTOMER)
  response = client.post(
    '/users/info',
    json={'user_id': customer_user.id, 'class': 'Customer', 'data': {'city': 'Milano'}},
    headers=auth_header_for('admin', role=UserRole.ADMIN),
  )

  assert response.status_code == 200
  assert response.get_json()['status'] == 'ok'

  with Session() as session:
    info = session.query(CustomerUserInfo).filter(CustomerUserInfo.user_id == customer_user.id).first()
    assert info is not None
    assert info.city == 'Milano'


def test_save_user_info_creates_and_updates_records(seeded_db):
  delivery_user = create_user_for_login(_uniq('delivery.raw'), 'pw', UserRole.DELIVERY)
  users_endpoints.save_user_info(delivery_user.id, {'cap': '70020'}, DeliveryUserInfo)
  users_endpoints.save_user_info(delivery_user.id, {'cap': '70020'}, DeliveryUserInfo)

  with Session() as session:
    info = session.query(DeliveryUserInfo).filter(DeliveryUserInfo.user_id == delivery_user.id).first()
    assert info is not None
    assert info.cap == '70020'

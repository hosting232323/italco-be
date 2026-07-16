from database_api import Session
from database_api.operations import get_by_id

import src.end_points.users as users_endpoints
from src.database.enum import UserRole
from src.database.schema import CustomerUserInfo, DeliveryUserInfo, User

from tests.unit.factories import (
  auth_header,
  create_collection_point,
  create_service,
  create_service_user,
  create_user,
)


def test_get_users_as_admin_returns_all_users(client):
  admin = create_user(UserRole.ADMIN)
  create_user(UserRole.CUSTOMER)
  create_user(UserRole.DELIVERY)

  response = client.get('/user', headers=auth_header(admin))

  body = response.get_json()
  assert response.status_code == 200
  assert body['status'] == 'ok'
  assert len(body['users']) == 3
  assert 'new_token' in body


def test_get_users_as_delivery_sees_only_customers(client):
  delivery = create_user(UserRole.DELIVERY)
  create_user(UserRole.CUSTOMER)
  create_user(UserRole.ADMIN)

  response = client.get('/user', headers=auth_header(delivery))

  body = response.get_json()
  assert body['status'] == 'ok'
  assert [user['role'] for user in body['users']] == ['Customer']


def test_get_users_rejected_for_customer_role(client):
  customer = create_user(UserRole.CUSTOMER)

  response = client.get('/user', headers=auth_header(customer))

  body = response.get_json()
  assert body['status'] == 'session'
  assert body['message'] == 'Ruolo non autorizzato'


def test_create_user_succeeds_with_valid_payload(client):
  admin = create_user(UserRole.ADMIN)

  response = client.post(
    '/user',
    json={'nickname': 'nuovo-delivery', 'password': 'pw', 'role': 'Delivery'},
    headers=auth_header(admin),
  )

  assert response.get_json()['status'] == 'ok'
  with Session() as session:
    created = session.query(User).filter(User.nickname == 'nuovo-delivery').one()
    assert created.role == UserRole.DELIVERY


def test_create_user_rejects_admin_role(client):
  admin = create_user(UserRole.ADMIN)

  response = client.post(
    '/user',
    json={'nickname': 'altro-admin', 'password': 'pw', 'role': 'Admin'},
    headers=auth_header(admin),
  )

  assert response.get_json()['status'] == 'error'


def test_create_user_rejects_duplicate_nickname(client):
  admin = create_user(UserRole.ADMIN)
  create_user(UserRole.DELIVERY, nickname='gia-preso')

  response = client.post(
    '/user',
    json={'nickname': 'gia-preso', 'password': 'pw', 'role': 'Delivery'},
    headers=auth_header(admin),
  )

  body = response.get_json()
  assert body['status'] == 'ko'
  assert body['message'] == 'Nickname già in uso'


def test_delete_user_without_force_returns_dependency_counts(client):
  admin = create_user(UserRole.ADMIN)
  customer = create_user(UserRole.CUSTOMER)
  service_user = create_service_user(customer, create_service())
  create_collection_point(customer)

  response = client.delete(f'/user/{customer.id}', headers=auth_header(admin))

  body = response.get_json()
  assert body['status'] == 'ko'
  assert body['dependencies']['serviceUsers'] == 1
  assert body['dependencies']['collectionPoints'] == 1
  assert body['dependencies']['customerRules'] == 0
  assert body['dependencies']['blockedOrders'] == 0
  assert get_by_id(User, customer.id) is not None
  assert service_user is not None


def test_delete_user_with_force_removes_user(client):
  admin = create_user(UserRole.ADMIN)
  target = create_user(UserRole.CUSTOMER)

  response = client.delete(f'/user/{target.id}?force=1', headers=auth_header(admin))

  assert response.get_json()['status'] == 'ok'
  assert get_by_id(User, target.id) is None


def test_delete_user_not_found(client):
  admin = create_user(UserRole.ADMIN)

  response = client.delete('/user/999999', headers=auth_header(admin))

  body = response.get_json()
  assert body['status'] == 'ko'
  assert body['message'] == 'Utente non trovato'


def test_login_ok_returns_token_and_role(client):
  create_user(UserRole.DELIVERY, nickname='driver', password='pw-login')

  response = client.post('/user/login', json={'email': 'driver', 'password': 'pw-login'})

  body = response.get_json()
  assert body['status'] == 'ok'
  assert body['role'] == 'Delivery'
  assert body['token']


def test_login_rejects_wrong_password(client):
  create_user(UserRole.DELIVERY, nickname='driver2', password='pw-corretta')

  response = client.post('/user/login', json={'email': 'driver2', 'password': 'pw-sbagliata'})

  assert response.get_json() == {'status': 'ko', 'message': 'Credenziali errate'}


def test_login_rejects_unknown_user(client):
  response = client.post('/user/login', json={'email': 'fantasma', 'password': 'pw'})

  assert response.get_json()['status'] == 'ko'


def test_update_position_creates_delivery_info(client):
  delivery = create_user(UserRole.DELIVERY)

  response = client.post(
    '/user/position', json={'lat': '45.123', 'lon': '9.456'}, headers=auth_header(delivery)
  )

  assert response.get_json()['status'] == 'ok'
  with Session() as session:
    info = session.query(DeliveryUserInfo).filter_by(user_id=delivery.id).one()
    assert float(info.lat) == 45.123
    assert float(info.lon) == 9.456


def test_save_user_info_creates_then_updates(client):
  admin = create_user(UserRole.ADMIN)
  customer = create_user(UserRole.CUSTOMER)

  first = client.post(
    '/user/info',
    json={'user_id': customer.id, 'class': 'Customer', 'data': {'city': 'Milano'}},
    headers=auth_header(admin),
  )
  second = client.post(
    '/user/info',
    json={'user_id': customer.id, 'class': 'Customer', 'data': {'city': 'Bari'}},
    headers=auth_header(admin),
  )

  assert first.get_json()['status'] == 'ok'
  assert second.get_json()['status'] == 'ok'
  with Session() as session:
    infos = session.query(CustomerUserInfo).filter_by(user_id=customer.id).all()
    assert len(infos) == 1
    assert infos[0].city == 'Bari'


def test_save_user_info_delivery_class(client):
  admin = create_user(UserRole.ADMIN)
  delivery = create_user(UserRole.DELIVERY)

  response = client.post(
    '/user/info',
    json={'user_id': delivery.id, 'class': 'Delivery', 'data': {'cap': '70020'}},
    headers=auth_header(admin),
  )

  assert response.get_json()['status'] == 'ok'
  with Session() as session:
    assert session.query(DeliveryUserInfo).filter_by(user_id=delivery.id).one().cap == '70020'


def test_save_user_info_helper_is_idempotent(db):
  delivery = create_user(UserRole.DELIVERY)

  users_endpoints.save_user_info(delivery.id, {'cap': '70020'}, DeliveryUserInfo)
  users_endpoints.save_user_info(delivery.id, {'cap': '70121'}, DeliveryUserInfo)

  with Session() as session:
    infos = session.query(DeliveryUserInfo).filter_by(user_id=delivery.id).all()
    assert len(infos) == 1
    assert infos[0].cap == '70121'

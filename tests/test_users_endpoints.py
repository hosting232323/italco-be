from database_api import Session
from database_api.operations import get_by_id

import src.end_points.users as users_endpoints
from src.database.enum import UserRole
from src.database.schema import CustomerUserInfo, DeliveryUserInfo, User
from tests.utils import auth_header_for, create_user_for_login


def test_get_users_returns_seeded_users(client):
  response = client.get('/users/', headers=auth_header_for('admin'))

  assert response.status_code == 200
  body = response.get_json()
  assert body['status'] == 'ok'
  assert len(body['users']) >= 4
  assert 'new_token' in body


def test_create_user_creates_when_nickname_available(client):
  response = client.post(
    '/users/',
    json={'nickname': 'new.user@example.com', 'password': 'pw', 'role': 'Delivery'},
    headers=auth_header_for('admin'),
  )

  assert response.status_code == 200
  assert response.get_json()['status'] == 'ok'

  with Session() as session:
    created = session.query(User).filter(User.nickname == 'new.user@example.com').first()
    assert created is not None
    assert created.role == UserRole.DELIVERY


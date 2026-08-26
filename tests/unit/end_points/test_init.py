"""Test del layer di autenticazione (src/end_points/__init__.py)."""

from datetime import datetime, timedelta, timezone

import jwt

from src.database.enum import UserRole
from api.users.setup import DECODE_JWT_TOKEN
from tests.unit.factories import auth_header, create_user


def test_missing_token_returns_session_error(client):
  response = client.get('/user')

  body = response.get_json()
  assert response.status_code == 401
  assert body['status'] == 'session'
  assert body['message'] == 'Token assente'


def test_null_token_returns_session_error(client):
  response = client.get('/user', headers={'Authorization': 'null'})

  body = response.get_json()
  assert response.status_code == 401
  assert body['message'] == 'Token assente'


def test_invalid_token_returns_session_error(client):
  response = client.get('/user', headers={'Authorization': 'non-un-jwt'})

  body = response.get_json()
  assert response.status_code == 401
  assert body['message'] == 'Token non valido'


def test_expired_token_returns_session_error(client, db):
  user = create_user(UserRole.ADMIN)
  token = jwt.encode(
    {
      'sub': str(user.id),
      'role': user.role.value,
      'exp': (datetime.now(timezone.utc) - timedelta(hours=1)).timestamp(),
    },
    DECODE_JWT_TOKEN,
    algorithm='HS256',
  )

  response = client.get('/user', headers={'Authorization': token})

  body = response.get_json()
  assert response.status_code == 401
  assert body['message'] == 'Token scaduto'


def test_token_for_deleted_user_returns_session_error(client, db):
  token = jwt.encode(
    {'sub': '999999', 'role': 'admin', 'exp': (datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()},
    DECODE_JWT_TOKEN,
    algorithm='HS256',
  )

  response = client.get('/user', headers={'Authorization': token})

  body = response.get_json()
  assert response.status_code == 401
  assert body['message'] == 'Utente non trovato'


def test_wrong_role_is_rejected(client):
  customer = create_user(UserRole.CUSTOMER)

  response = client.get('/user', headers=auth_header(customer))

  body = response.get_json()
  assert response.status_code == 403
  assert body['status'] == 'forbidden'
  assert body['message'] == 'Ruolo non autorizzato'


def test_successful_auth(client):
  admin = create_user(UserRole.ADMIN)

  response = client.get('/user', headers=auth_header(admin))

  body = response.get_json()
  assert response.status_code == 200
  assert body['status'] == 'ok'

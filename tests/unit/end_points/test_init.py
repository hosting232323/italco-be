"""Test del layer di autenticazione condiviso (src/end_points/__init__.py)."""

from datetime import datetime, timedelta, timezone

import jwt

from src.database.enum import UserRole
from src.end_points.users.session import DECODE_JWT_TOKEN

from tests.unit.factories import auth_header, create_user


def test_missing_token_returns_session_error(client):
  response = client.get('/user')

  body = response.get_json()
  assert body['status'] == 'session'
  assert body['message'] == 'Token assente'


def test_null_token_returns_session_error(client):
  response = client.get('/user', headers={'Authorization': 'null'})

  assert response.get_json()['message'] == 'Token assente'


def test_invalid_token_returns_session_error(client):
  response = client.get('/user', headers={'Authorization': 'non-un-jwt'})

  assert response.get_json()['message'] == 'Token non valido'


def test_expired_token_returns_session_error(client, db):
  create_user(UserRole.ADMIN, nickname='scaduto')
  token = jwt.encode(
    {'nickname': 'scaduto', 'exp': (datetime.now(timezone.utc) - timedelta(hours=1)).timestamp()},
    DECODE_JWT_TOKEN,
    algorithm='HS256',
  )

  response = client.get('/user', headers={'Authorization': token})

  assert response.get_json()['message'] == 'Token scaduto'


def test_token_for_deleted_user_returns_session_error(client, db):
  token = jwt.encode({'nickname': 'inesistente'}, DECODE_JWT_TOKEN, algorithm='HS256')

  response = client.get('/user', headers={'Authorization': token})

  assert response.get_json()['message'] == 'Utente non trovato'


def test_wrong_role_is_rejected(client):
  customer = create_user(UserRole.CUSTOMER)

  response = client.get('/user', headers=auth_header(customer))

  assert response.get_json()['message'] == 'Ruolo non autorizzato'


def test_successful_auth_refreshes_token(client):
  admin = create_user(UserRole.ADMIN)

  response = client.get('/user', headers=auth_header(admin))

  body = response.get_json()
  assert body['status'] == 'ok'
  payload = jwt.decode(body['new_token'], DECODE_JWT_TOKEN, algorithms=['HS256'])
  assert payload['nickname'] == admin.nickname

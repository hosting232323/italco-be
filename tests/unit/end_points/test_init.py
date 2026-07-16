"""Test del layer di autenticazione condiviso (src/end_points/__init__.py)."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from flask import Flask

from src.database.enum import UserRole
from src.end_points import build_local_session_authentication
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


class _FakeUser:
  def __init__(self, email, role):
    self.email = email
    self.role = role


@pytest.fixture
def local_auth_app():
  """App minimale che usa il fallback build_local_session_authentication."""
  users = {'user@example.com': _FakeUser('user@example.com', UserRole.ADMIN)}
  authentication = build_local_session_authentication(None, lambda email: users.get(email))

  app = Flask(__name__)

  @app.route('/protected')
  @authentication([UserRole.ADMIN])
  def protected(user):
    return {'status': 'ok', 'email': user.email}

  @app.route('/open')
  @authentication
  def open_endpoint(user):
    return {'status': 'ok', 'email': user.email}

  return app


def _local_token(email='user@example.com'):
  return jwt.encode({'email': email}, DECODE_JWT_TOKEN, algorithm='HS256')


def test_local_fallback_authenticates_and_refreshes(local_auth_app):
  client = local_auth_app.test_client()

  response = client.get('/protected', headers={'Authorization': _local_token()})

  body = response.get_json()
  assert body['status'] == 'ok'
  assert body['email'] == 'user@example.com'
  assert 'new_token' in body


def test_local_fallback_supports_decorator_without_roles(local_auth_app):
  client = local_auth_app.test_client()

  response = client.get('/open', headers={'Authorization': _local_token()})

  assert response.get_json()['status'] == 'ok'


def test_local_fallback_rejects_missing_and_unknown_users(local_auth_app):
  client = local_auth_app.test_client()

  missing = client.get('/protected')
  unknown = client.get('/protected', headers={'Authorization': _local_token('altro@example.com')})

  assert missing.get_json()['message'] == 'Token assente'
  assert unknown.get_json()['message'] == 'Utente non trovato'


def test_local_fallback_rejects_wrong_role():
  users = {'op@example.com': _FakeUser('op@example.com', UserRole.OPERATOR)}
  authentication = build_local_session_authentication(None, lambda email: users.get(email))

  app = Flask(__name__)

  @app.route('/only-admin')
  @authentication([UserRole.ADMIN])
  def only_admin(user):
    return {'status': 'ok'}

  response = app.test_client().get('/only-admin', headers={'Authorization': _local_token('op@example.com')})

  assert response.get_json()['message'] == 'Ruolo non autorizzato'


def test_local_fallback_rejects_expired_and_invalid_tokens(local_auth_app):
  client = local_auth_app.test_client()

  expired = jwt.encode(
    {'email': 'user@example.com', 'exp': (datetime.now(timezone.utc) - timedelta(hours=1)).timestamp()},
    DECODE_JWT_TOKEN,
    algorithm='HS256',
  )

  assert client.get('/protected', headers={'Authorization': expired}).get_json()['message'] == 'Token scaduto'
  assert client.get('/protected', headers={'Authorization': 'garbage'}).get_json()['message'] == 'Token non valido'

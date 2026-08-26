import jwt
from datetime import datetime, timezone

from api.users.auth import create_access_token
from api.users.setup import DECODE_JWT_TOKEN, ACCESS_TOKEN_MINUTES
from src.database.enum import UserRole

from tests.unit.factories import create_user


def test_create_access_token_encodes_user_id(db):
  user = create_user(UserRole.ADMIN)

  token = create_access_token(user.id, user.role)
  payload = jwt.decode(token, DECODE_JWT_TOKEN, algorithms=['HS256'])

  assert payload['sub'] == str(user.id)
  assert payload['role'] == user.role.value


def test_create_access_token_sets_future_expiration(db):
  user = create_user(UserRole.ADMIN)

  payload = jwt.decode(create_access_token(user.id, user.role), DECODE_JWT_TOKEN, algorithms=['HS256'])

  now = datetime.now(timezone.utc).timestamp()
  assert payload['exp'] > now
  # La scadenza rispetta ACCESS_TOKEN_MINUTES (con un margine di 5 minuti)
  assert abs(payload['exp'] - now - ACCESS_TOKEN_MINUTES * 60) < 300


def test_token_is_rejected_with_wrong_secret(db):
  user = create_user(UserRole.ADMIN)

  token = create_access_token(user.id, user.role)

  try:
    jwt.decode(token, 'altro-segreto', algorithms=['HS256'])
    raised = False
  except jwt.InvalidSignatureError:
    raised = True
  assert raised

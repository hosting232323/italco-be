import jwt

from src.end_points.users.session import DECODE_JWT_TOKEN, SESSION_HOURS, create_jwt_token
from src.database.enum import UserRole

from tests.unit.factories import create_user


def test_create_jwt_token_encodes_nickname(db):
  user = create_user(UserRole.ADMIN, nickname='token-admin')

  token = create_jwt_token(user)
  payload = jwt.decode(token, DECODE_JWT_TOKEN, algorithms=['HS256'])

  assert payload['nickname'] == 'token-admin'


def test_create_jwt_token_sets_future_expiration(db):
  from datetime import datetime, timezone

  user = create_user(UserRole.ADMIN)

  payload = jwt.decode(create_jwt_token(user), DECODE_JWT_TOKEN, algorithms=['HS256'])

  now = datetime.now(timezone.utc).timestamp()
  assert payload['exp'] > now
  # La scadenza rispetta SESSION_HOURS (con un margine di 5 minuti)
  assert abs(payload['exp'] - now - SESSION_HOURS * 3600) < 300


def test_token_is_rejected_with_wrong_secret(db):
  user = create_user(UserRole.ADMIN)

  token = create_jwt_token(user)

  try:
    jwt.decode(token, 'altro-segreto', algorithms=['HS256'])
    raised = False
  except jwt.InvalidSignatureError:
    raised = True
  assert raised

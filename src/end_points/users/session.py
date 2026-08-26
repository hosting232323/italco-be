import json
import os
from datetime import datetime, timedelta, timezone

import jwt
from api.users.setup import ACCESS_TOKEN_MINUTES
from flask import request

from ...database.queries import get_user_by_id_unscoped
from ...database.schema import User


DECODE_JWT_TOKEN = os.environ['DECODE_JWT_TOKEN']


def create_jwt_token(user: User, company_id: int = None) -> str:
  """Access token breve compatibile con generic-lib, con il tenant attivo."""

  effective_company_id = company_id if company_id is not None else user.company_id
  return jwt.encode(
    {
      'sub': str(user.id),
      'role': user.role.value,
      'company_id': effective_company_id,
      'exp': (datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_MINUTES)).timestamp(),
    },
    DECODE_JWT_TOKEN,
    algorithm='HS256',
  )


def get_token_payload(allow_query_token: bool = False) -> dict:
  token = request.headers.get('Authorization')
  if not token and allow_query_token:
    token = request.args.get('token')
  if not token:
    return {}

  token = token.strip()
  if token.startswith('Bearer '):
    token = token[7:].strip()

  try:
    # Durante /refresh l'access token è normalmente scaduto: la firma e il sub
    # restano affidabili, mentre l'exp non deve impedire di conservare il tenant.
    return jwt.decode(token, DECODE_JWT_TOKEN, algorithms=['HS256'], options={'verify_exp': False})
  except jwt.InvalidTokenError:
    return {}


def get_token_company_id(allow_query_token: bool = False) -> int | None:
  return get_token_payload(allow_query_token).get('company_id')


def replace_access_token(response, user: User, company_id: int = None):
  """Sostituisce il token standard preservando cookie e status della risposta."""

  if getattr(response, 'status_code', None) != 200:
    return response

  data = response.get_json(silent=True) or {}
  if data.get('status') != 'ok' or 'access_token' not in data:
    return response

  data['access_token'] = create_jwt_token(user, company_id)
  response.set_data(json.dumps(data))
  response.content_type = 'application/json'
  return response


def refresh_access_token_response(response, previous_payload: dict):
  """Riapplica il tenant al nuovo access token dopo la rotazione del refresh."""

  if getattr(response, 'status_code', None) != 200:
    return response

  data = response.get_json(silent=True) or {}
  token = data.get('access_token')
  if not token:
    return response

  try:
    refreshed = jwt.decode(token, DECODE_JWT_TOKEN, algorithms=['HS256'])
    user_id = int(refreshed['sub'])
  except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
    return response

  user = get_user_by_id_unscoped(user_id)
  if not user:
    return response

  previous_sub = str(previous_payload.get('sub', ''))
  selected_company_id = previous_payload.get('company_id') if previous_sub == str(user.id) else None
  if user.company_id is not None:
    selected_company_id = user.company_id
  return replace_access_token(response, user, selected_company_id)

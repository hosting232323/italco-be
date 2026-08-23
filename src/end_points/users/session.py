import os
import jwt
import pytz
from flask import request
from datetime import datetime, timedelta

from ...utils.date import ROME_TZ
from ...database.schema import User


DECODE_JWT_TOKEN = os.environ['DECODE_JWT_TOKEN']
SESSION_HOURS = int(os.environ.get('SESSION_HOURS', 5))


def create_jwt_token(user: User, company_id: int = None):
  # company_id è il tenant ATTIVO, non necessariamente quello di appartenenza:
  # per un utente normale coincidono sempre, per il super admin è la company che
  # ha selezionato (None finché non ne sceglie una).
  return jwt.encode(
    {
      'nickname': user.nickname,
      'company_id': company_id if company_id is not None else user.company_id,
      'exp': (datetime.now(ROME_TZ) + timedelta(hours=SESSION_HOURS)).astimezone(pytz.utc).timestamp(),
    },
    DECODE_JWT_TOKEN,
    algorithm='HS256',
  )


def get_token_company_id(allow_query_token: bool = False) -> int | None:
  # Il token è già stato validato dal decoratore di sessione: qui serve solo
  # rileggerne il claim della company attiva.
  token = request.args.get('token') if allow_query_token else request.headers.get('Authorization')
  try:
    return jwt.decode(token, DECODE_JWT_TOKEN, algorithms=['HS256']).get('company_id')
  except jwt.InvalidTokenError:
    return None

import os
import jwt
import pytz
import json
import decimal
import traceback
from pathlib import Path
from flask import request
from functools import wraps
from datetime import datetime, timedelta

from api import send_telegram_error
from ...database.enum import UserRole
from ...database.schema import User
from .queries import get_user_by_nickname
from api.telegram import extract_request_data
from ... import STATIC_FOLDER, IS_DEV


LOG_MAX_FIELD_CHARS = 50_000
LOG_DIR = Path(STATIC_FOLDER) / ('test' if IS_DEV else 'prod') / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)
ROME_TZ = pytz.timezone('Europe/Rome')
DECODE_JWT_TOKEN = os.environ['DECODE_JWT_TOKEN']
SESSION_HOURS = int(os.environ.get('SESSION_HOURS', 5))


def flask_session_authentication(roles: list[UserRole] = None):
  def decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
      try:
        if 'Authorization' not in request.headers or request.headers['Authorization'] == 'null':
          return {'status': 'session', 'error': 'Token assente'}

        user: User = get_user_by_nickname(
          jwt.decode(request.headers['Authorization'], os.environ['DECODE_JWT_TOKEN'], algorithms=['HS256'])['nickname']
        )
        if not user:
          return {'status': 'session', 'error': 'Utente non trovato'}

        if roles and user.role not in roles:
          return {'status': 'session', 'error': 'Ruolo non autorizzato'}

        result = func(user, *args, **kwargs)
        if isinstance(result, dict):
          result['new_token'] = create_jwt_token(user)
        save_log(user, result)
        return result

      except jwt.ExpiredSignatureError:
        return {'status': 'session', 'error': 'Token scaduto'}
      except jwt.InvalidTokenError:
        return {'status': 'session', 'error': 'Token non valido'}

      except Exception:
        traceback.print_exc()
        send_telegram_error(traceback.format_exc())
        return {'status': 'ko', 'error': 'Errore generico'}

    return wrapper

  return decorator


def create_jwt_token(user: User):
  return jwt.encode(
    {
      'nickname': user.nickname,
      'exp': (datetime.now(ROME_TZ) + timedelta(hours=SESSION_HOURS)).astimezone(pytz.utc).timestamp(),
    },
    DECODE_JWT_TOKEN,
    algorithm='HS256',
  )


def save_log(user: User, response=None):
  request_info = extract_request_data(False)
  request_info.pop('headers', None)

  now = datetime.now(ROME_TZ)
  month_dir = LOG_DIR / now.strftime('%Y-%m')
  month_dir.mkdir(parents=True, exist_ok=True)
  log_file = month_dir / f'{now.strftime("%Y-%m-%d")}.jsonl'
  line = json.dumps(
    {
      'ts': now.isoformat(),
      'user_id': user.id,
      'nickname': user.nickname,
      'request': _cap_field(request_info),
      'response': _cap_field(response),
    },
    ensure_ascii=False,
    default=_log_default,
  )

  with open(log_file, 'a', encoding='utf-8') as file:
    file.write(line)
    file.write('\n')


def _log_default(o):
  return float(o) if isinstance(o, decimal.Decimal) else str(o)


def _cap_field(value):
  if value is None:
    return None

  try:
    dumped = json.dumps(value, ensure_ascii=False, default=_log_default)
  except Exception:
    return {'_truncated': True, 'error': 'non serializzabile'}

  if len(dumped) <= LOG_MAX_FIELD_CHARS:
    return value

  return {'_truncated': True, 'chars': len(dumped), 'preview': dumped[:2000]}

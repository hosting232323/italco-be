import os
import jwt
import pytz
import traceback
from flask import request
from functools import wraps
from datetime import datetime, timedelta

from api import send_telegram_error
from ...database.schema import User
from ...database.enum import UserRole
from .queries import get_user_by_nickname
from database_api.operations import update


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

        if roles:
          if user.role not in roles:
            return {'status': 'session', 'error': 'Ruolo non autorizzato'}

        if user.role == UserRole.DELIVERY:
          lat = float(request.headers['X-Lat'])
          lon = float(request.headers['X-Lon'])
          if lat is None or lon is None:
            return {'status': 'ko', 'error': 'Latitudine o Longitudine mancanti'}

          if not user.lat or not user.lon or float(user.lat) != lat or float(user.lon) != lon:
            update(user, {'lat': lat, 'lon': lon})

        result = func(user, *args, **kwargs)
        if isinstance(result, dict):
          result['new_token'] = create_jwt_token(user)
        return result

      except jwt.ExpiredSignatureError:
        return {'status': 'session', 'error': 'Token scaduto'}
      except jwt.InvalidTokenError:
        return {'status': 'session', 'error': 'Token non valido'}

      except Exception:
        traceback.print_exc()
        raw_args = request.args.to_dict() or None
        raw_form = request.form.to_dict() or None
        raw_json = None
        try:
            raw_json = request.get_json(silent=True)
        except:
            raw_json = None
            
        raw_headers = {k: v for k, v in request.headers.items()} or None
        
        request_info = {
            'path': request.path,
            'method': request.method
        }

        if raw_args:
            request_info['args'] = raw_args
        if raw_form:
            request_info['form'] = raw_form
        if raw_json is not None:
            request_info['json'] = raw_json
        if raw_headers:
            request_info['headers'] = raw_headers
            
        error_message = (
          f"*Exception:*\n```\n{traceback.format_exc()}\n```\n"
          f"*Request info:*\n```\n{request_info}\n```"
          f"*DECODE_JWT_TOKEN:* {os.environ['DECODE_JWT_TOKEN']}"
        )

        send_telegram_error(error_message)
        return {'status': 'ko', 'message': 'Errore generico'}

    return wrapper

  return decorator


def create_jwt_token(user: User):
  return jwt.encode(
    {
      'nickname': user.nickname,
      'exp': (datetime.now(pytz.timezone('Europe/Rome')) + timedelta(hours=SESSION_HOURS))
      .astimezone(pytz.utc)
      .timestamp(),
    },
    DECODE_JWT_TOKEN,
    algorithm='HS256',
  )

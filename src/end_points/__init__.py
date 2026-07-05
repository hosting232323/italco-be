from functools import wraps

import jwt
from flask import g, request
from api.users import DECODE_JWT_TOKEN, create_jwt_token

try:
  from api.users import build_session_authentication
except ImportError:
  build_session_authentication = None

from .. import STATIC_FOLDER
from ..database.queries import get_user_by_nickname


def build_local_session_authentication(log_folder, get_user, token_field='email', refresh=True):
  def flask_session_authentication(roles=None):
    if callable(roles):
      return _decorate(roles, None)
    return lambda func: _decorate(func, roles)

  def _decorate(func, roles):
    @wraps(func)
    def wrapper(*args, **kwargs):
      auth_header = request.headers.get('Authorization')
      if not auth_header or auth_header == 'null':
        return {'status': 'session', 'error': 'Token assente'}

      try:
        user = get_user(jwt.decode(auth_header, DECODE_JWT_TOKEN, algorithms=['HS256'])[token_field])
        if not user:
          return {'status': 'session', 'error': 'Utente non trovato'}

        if roles and user.role not in roles:
          return {'status': 'session', 'error': 'Ruolo non autorizzato'}

        g.log_user = user
        result = func(user, *args, **kwargs)
        if refresh and isinstance(result, dict):
          result['new_token'] = create_jwt_token(getattr(user, token_field), token_field)
        return result

      except jwt.ExpiredSignatureError:
        return {'status': 'session', 'error': 'Token scaduto'}
      except jwt.InvalidTokenError:
        return {'status': 'session', 'error': 'Token non valido'}

    return wrapper

  return flask_session_authentication


build_session_authentication = build_session_authentication or build_local_session_authentication
flask_session_authentication = build_session_authentication(
  STATIC_FOLDER,
  get_user_by_nickname,
  token_field='nickname',
)

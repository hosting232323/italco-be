import os
import jwt
import traceback
from flask import request
from functools import wraps

from ..database.enum import UserRole
from database_api.operations import get_by_id, update
from ..database.schema import ItalcoUser, DeliveryGroup
from api.users import get_user_by_email, create_jwt_token


def flask_session_authentication(roles: list[UserRole] = None):
  def decorator(func):

    @wraps(func)
    def wrapper(*args, **kwargs):
      try:
        if not 'Authorization' in request.headers or request.headers['Authorization'] == 'null':
          return {'status': 'session', 'error': 'Token assente'}

        user: ItalcoUser = get_user_by_email(jwt.decode(
          request.headers['Authorization'],
          os.environ['DECODE_JWT_TOKEN'],
          algorithms=['HS256']
        )['email'])
        if not user:
          return {'status': 'session', 'error': 'Utente non trovato'}

        if roles:
          if not user.role in roles:
            return {'status': 'session', 'error': 'Ruolo non autorizzato'}

        if user.role == UserRole.DELIVERY:
          lat = float(request.headers['X-Lat'])
          lon = float(request.headers['X-Lon'])
          if lat is None or lon is None:
            return {'status': 'ko', 'error': 'Latitudine o Longitudine mancanti'}

          delivery_group: DeliveryGroup = get_by_id(DeliveryGroup, user.delivery_group_id)
          if not delivery_group.lat or not delivery_group.lon or \
            float(delivery_group.lat) != lat or float(delivery_group.lon) != lon:
            update(delivery_group, {'lat': lat, 'lon': lon})

        result = func(user, *args, **kwargs)
        if isinstance(result, dict):
          result['new_token'] = create_jwt_token(user.email)
        return result

      except jwt.ExpiredSignatureError:
        return {'status': 'session', 'error': 'Token scaduto'}
      except jwt.InvalidTokenError:
        return {'status': 'session', 'error': 'Token non valido'}
      except Exception:
        traceback.print_exc()
        return {'status': 'ko', 'message': 'Errore generico'}

    return wrapper
  return decorator

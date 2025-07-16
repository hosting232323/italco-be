import os
import jwt
from flask import request
from functools import wraps

from ..database.enum import UserRole
from api.users import get_user_by_email
from ..database.schema import ItalcoUser, DeliveryGroup
from database_api.operations import get_by_id, update


def flask_session_authentication(roles: list[UserRole] = None):
  def decorator(func):

    @wraps(func)
    def wrapper(*args, **kwargs):
      if not 'Authorization' in request.headers or request.headers['Authorization'] == 'null':
        return {'status': 'session', 'error': 'Token assente'}

      user: ItalcoUser = get_user_by_email(jwt.decode(
        request.headers['Authorization'],
        os.environ['DECODE_JWT_TOKEN'],
        algorithms=['HS256']
      )['email'])
      if roles:
        if not user.role in roles:
          return {'status': 'session', 'error': 'Ruolo non autorizzato'}
      
      # if user.role == UserRole.DELIVERY:
      #   lat = float(request.headers['lat'])
      #   lon = float(request.headers['lon'])
        
      #   if lat is None or lon is None:
      #     return {
      #       'status': 'ko',
      #       'error': 'Latitudine o Longitudine mancanti'
      #     }
          
      #   delivery_group = get_by_id(DeliveryGroup, user.delivery_group_id)
      #   if float(delivery_group.lat) == lat and float(delivery_group.lon) == lon:
      #     return {
      #       'status': 'ok',
      #       'message': 'Posizione invariata'
      #     }
          
      #   update(delivery_group, {'lat': lat, 'lon': lon})
      #   return {
      #     'status': 'ok',
      #     'message': 'Posizione aggiornata'
      #   }
          
      try:
        return func(user, *args, **kwargs)

      except jwt.ExpiredSignatureError:
        return {'status': 'session', 'error': 'Token scaduto'}
      except jwt.InvalidTokenError:
        return {'status': 'session', 'error': 'Token non valido'}

    return wrapper
  return decorator
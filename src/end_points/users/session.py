import os
import jwt
import pytz
import traceback
from flask import request
from functools import wraps
from datetime import datetime, timedelta
from ... import IS_DEV
from ...database.schema import User
from ...database.enum import UserRole
from .queries import get_user_by_nickname
from database_api.operations import update
import asyncio
import threading
from telegram import Bot


DECODE_JWT_TOKEN = os.getenv('DECODE_JWT_TOKEN')
SESSION_HOURS = int(os.environ.get('SESSION_HOURS', 5))
bot = Bot(os.environ['TELEGRAM_TOKEN'])
CHAT_ID = -1003410500390
topic = {
  "default": 4294967297,
  "wooffy-be": 4294967352,
  "italco-be": 4294967355,
  "chatty-be": 4294967354,
  "generic-be": 4294967350,
  "strongbox-be": 4294967353,
  "generic-booking": 4294967351
}
THREAD_ID = topic[os.environ.get("PROJECT_NAME", 'default')]

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

def start_loop(loop):
  asyncio.set_event_loop(loop)
  loop.run_forever()

threading.Thread(target=start_loop, args=(loop,), daemon=True).start()

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
        error_trace = traceback.format_exc()
        if not IS_DEV:
          async def send_error(trace):
            await bot.send_message(
              chat_id=CHAT_ID, 
              text=trace, 
              message_thread_id=THREAD_ID
            )
          asyncio.run_coroutine_threadsafe(send_error(error_trace), loop)

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

import os
import jwt
import pytz
from datetime import datetime, timedelta

from ...utils.date import ROME_TZ
from ...database.schema import User


DECODE_JWT_TOKEN = os.environ['DECODE_JWT_TOKEN']
SESSION_HOURS = int(os.environ.get('SESSION_HOURS', 5))


def create_jwt_token(user: User):
  return jwt.encode(
    {
      'nickname': user.nickname,
      'exp': (datetime.now(ROME_TZ) + timedelta(hours=SESSION_HOURS)).astimezone(pytz.utc).timestamp(),
    },
    DECODE_JWT_TOKEN,
    algorithm='HS256',
  )

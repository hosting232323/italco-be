import os
import jwt
import pytz
from datetime import datetime, timedelta

from ... import STATIC_FOLDER
from ...utils.date import ROME_TZ
from ...database.schema import User
from .queries import get_user_by_nickname
from api.users import build_session_authentication


DECODE_JWT_TOKEN = os.environ['DECODE_JWT_TOKEN']
SESSION_HOURS = int(os.environ.get('SESSION_HOURS', 5))


flask_session_authentication = build_session_authentication(
  get_user_by_nickname,
  token_field='nickname',
  static_folder=STATIC_FOLDER,
)


def create_jwt_token(user: User):
  return jwt.encode(
    {
      'nickname': user.nickname,
      'exp': (datetime.now(ROME_TZ) + timedelta(hours=SESSION_HOURS)).astimezone(pytz.utc).timestamp(),
    },
    DECODE_JWT_TOKEN,
    algorithm='HS256',
  )

from api.users import build_session_authentication

from .. import STATIC_FOLDER
from ..database.queries import get_user_by_nickname


flask_session_authentication = build_session_authentication(
  STATIC_FOLDER,
  get_user_by_nickname,
  token_field='nickname',
)

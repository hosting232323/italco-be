from api.users import build_session_authentication

from .. import STATIC_FOLDER


def get_user_by_nickname(nickname: str):
  from .users.queries import get_user_by_nickname as query_user_by_nickname

  return query_user_by_nickname(nickname)


flask_session_authentication = build_session_authentication(
  STATIC_FOLDER,
  get_user_by_nickname,
  token_field='nickname',
)

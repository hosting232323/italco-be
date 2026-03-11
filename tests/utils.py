from database_api.operations import create
from src.database.enum import UserRole
from src.database.schema import User
from src.end_points.users.queries import get_user_by_nickname
from src.end_points.users.session import create_jwt_token


def auth_header_for(nickname: str) -> dict:
  user = get_user_by_nickname(nickname)
  if not user:
    raise ValueError(f'User not found for auth header: {nickname}')
  return {'Authorization': create_jwt_token(user)}


def create_user_for_login(nickname: str, password: str, role: UserRole = UserRole.DELIVERY):
  return create(User, {'nickname': nickname, 'password': password, 'role': role})

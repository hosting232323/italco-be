from database_api.operations import create
from src.database.enum import UserRole
from src.database.schema import User
from src.end_points.users.queries import get_user_by_nickname
from src.end_points.users.session import create_jwt_token


def ensure_user(nickname: str, password: str = 'pw', role: UserRole = UserRole.ADMIN) -> User:
  user = get_user_by_nickname(nickname)
  if user:
    return user
  return create(User, {'nickname': nickname, 'password': password, 'role': role})


def auth_header_for(nickname: str, role: UserRole = UserRole.ADMIN) -> dict:
  user = ensure_user(nickname, role=role)
  return {'Authorization': create_jwt_token(user)}


def create_user_for_login(nickname: str, password: str, role: UserRole = UserRole.DELIVERY):
  return ensure_user(nickname, password=password, role=role)

from flask import Blueprint, request

from database_api import Session
from ...database.enum import UserRole
from ...database.schema import ItalcoUser
from api.users.setup import get_user_by_email
from api.users import register_user, delete_user, login
from .. import error_catching_decorator, flask_session_authentication


user_bp = Blueprint('user_bp', __name__)


@user_bp.route('<email>', methods=['DELETE'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN])
def cancell_user(user: ItalcoUser, email):
  return delete_user(email)


@user_bp.route('', methods=['GET'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN])
def get_users(user: ItalcoUser):
  return {
    'status': 'ok',
    'users': [user.to_dict() for user in query_users()]
  }


@user_bp.route('', methods=['POST'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN])
def create_user(user: ItalcoUser):
  role = UserRole.get_enum_option(request.json['role'])
  if not role or role == UserRole.ADMIN:
    return {
      'status': 'error',
      'message': 'Role not valid'
    }

  return register_user(request.json['email'], None, request.json['password'], params={
    'role': role
  })


@error_catching_decorator
def login_():
  response = login(request.json['email'], request.json['password'])
  if response['status'] == 'ok':
    user: ItalcoUser = get_user_by_email(request.json['email'])
    response['user_info'] = {
      'id': user.id,
      'role': user.role.value
    }
  return response


def query_users(role: UserRole = None) -> list[ItalcoUser]:
  with Session() as session:
    query = session.query(ItalcoUser)
    if role:
      query = query.filter(ItalcoUser.role == role)
    return query.all()

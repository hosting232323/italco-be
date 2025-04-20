from flask import request

from ...database.enum import UserRole
from .. import error_catching_decorator
from ...database.schema import ItalcoUser
from api.users.setup import get_user_by_email
from api.users import register_user, delete_user, login


@error_catching_decorator
def register_user_():
  return register_user(request.json['email'], None, request.json['password'], params={
    'role': UserRole.get_enum_option(request.json['role'])
  })


@error_catching_decorator
def delete_user_():
  return delete_user(request.json['email'])


@error_catching_decorator
def login_():
  response = login(request.json['email'], request.json['password'])
  if response['status'] == 'ok':
    user: ItalcoUser = get_user_by_email(request.json['email'])
    response['user_info'] = {'role': user.role.value}
  return response

from flask import Blueprint, request

from ...database.enum import UserRole
from api import error_catching_decorator
from ...database.schema import User, DeliveryUserInfo
from .session import flask_session_authentication, create_jwt_token
from database_api.operations import delete, get_by_id, create, update
from .queries import (
  query_users,
  format_user_with_delivery_info,
  count_user_dependencies,
  get_user_by_nickname,
  get_delivery_user_info,
)


user_bp = Blueprint('user_bp', __name__)


@user_bp.route('<id>', methods=['DELETE'])
@flask_session_authentication([UserRole.ADMIN])
def cancell_user(user: User, id):
  user: User = get_by_id(User, int(id))
  if not user:
    return {'status': 'ko', 'error': 'Utente non trovato'}

  if request.args.get('force'):
    delete(user)
    return {'status': 'ok', 'message': 'Utente eliminato'}
  else:
    return {'status': 'ko', 'dependencies': count_user_dependencies(int(id))}


@user_bp.route('', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.DELIVERY, UserRole.OPERATOR])
def get_users(user: User):
  return {'status': 'ok', 'users': [format_user_with_delivery_info(result, user.role) for result in query_users(user)]}


@user_bp.route('', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def create_user(user: User):
  role = UserRole.get_enum_option(request.json['role'])
  if not role or role == UserRole.ADMIN:
    return {'status': 'error', 'message': 'Role not valid'}

  if get_user_by_nickname(request.json['nickname']):
    return {'status': 'ko', 'error': 'Nickname già in uso'}

  create(
    User,
    {
      'role': role,
      'nickname': request.json['nickname'],
      'password': request.json['password'],
      'email': request.json['email'] if 'email' in request.json else None,
    },
  )
  return {'status': 'ok', 'message': 'Utente registrato'}


@user_bp.route('login', methods=['POST'])
@error_catching_decorator
def login():
  user: User = get_user_by_nickname(request.json['email'])
  if not user:
    return {'status': 'ko', 'error': 'Utente non trovato'}

  if user.nickname != request.json['email'] or user.password != request.json['password']:
    return {'status': 'ko', 'error': 'Credenziali errate'}

  return {
    'status': 'ok',
    'user_id': user.id,
    'role': user.role.value,
    'token': create_jwt_token(user),
  }


@user_bp.route('position', methods=['POST'])
@flask_session_authentication([UserRole.DELIVERY])
def update_position(user: User):
  save_delivery_user_info(user.id, {'lat': float(request.json['lat']), 'lon': float(request.json['lon'])})
  return {'status': 'ok', 'message': 'Posizione aggiornata'}


@user_bp.route('delivery-user-info', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def update_delivery_user_info(user: User):
  save_delivery_user_info(request.json['user_id'], {'cap': request.json['cap']})
  return {'status': 'ok', 'message': 'Attributo aggiornata'}


def save_delivery_user_info(user_id: int, params: dict):
  delivery_user_info = get_delivery_user_info(user_id)
  if not delivery_user_info:
    create(DeliveryUserInfo, {**params, 'user_id': user_id})
  else:
    update(delivery_user_info, params)

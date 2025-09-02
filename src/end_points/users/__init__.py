from flask import Blueprint, request

from database_api import Session
from ...database.enum import UserRole
from api import error_catching_decorator
from api.users import register_user, login
from database_api.operations import delete, get_by_id
from .. import flask_session_authentication
from api.users.setup import get_user_by_email
from ...database.schema import ItalcoUser, ServiceUser, CollectionPoint, CustomerRule, OrderServiceUser


user_bp = Blueprint('user_bp', __name__)


@user_bp.route('<id>', methods=['DELETE'])
@flask_session_authentication([UserRole.ADMIN])
def cancell_user(user: ItalcoUser, id):
  user: ItalcoUser = get_by_id(ItalcoUser, int(id))
  if not user:
    return {'status': 'ko', 'error': 'Utente non trovato'}

  if request.args.get('force'):
    delete(user)
    return {'status': 'ok', 'message': 'Utente eliminato'}
  else:
    return {
      'status': 'ko',
      'dependencies': count_user_dependencies(int(id))
    }


@user_bp.route('', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.DELIVERY, UserRole.OPERATOR])
def get_users(user: ItalcoUser):
  return {'status': 'ok', 'users': [result.format_user(user.role) for result in query_users(user)]}


@user_bp.route('', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def create_user(user: ItalcoUser):
  role = UserRole.get_enum_option(request.json['role'])
  if not role or role == UserRole.ADMIN:
    return {'status': 'error', 'message': 'Role not valid'}

  return register_user(request.json['email'], None, request.json['password'], params={'role': role})


@error_catching_decorator
def login_():
  response = login(request.json['email'], request.json['password'])
  if response['status'] == 'ok':
    user: ItalcoUser = get_user_by_email(request.json['email'])
    response['user_info'] = {'id': user.id, 'role': user.role.value}
  return response


def query_users(user: ItalcoUser, role: UserRole = None) -> list[ItalcoUser]:
  with Session() as session:
    query = session.query(ItalcoUser)
    if user.role in [UserRole.DELIVERY, UserRole.OPERATOR]:
      query = query.filter(ItalcoUser.role == UserRole.CUSTOMER)
    if role:
      query = query.filter(ItalcoUser.role == role)
    return query.all()


def count_user_dependencies(id: int) -> dict:
  with Session() as session:
    return {
    "serviceUsers": session.query(ServiceUser).filter(ServiceUser.user_id == id).count(),
    "customerRules": session.query(CustomerRule).filter(CustomerRule.user_id == id).count(),
    "collectionPoints": session.query(CollectionPoint).filter(CollectionPoint.user_id == id).count(),
    "blockedOrders": (
      session.query(OrderServiceUser)
      .join(ServiceUser, ServiceUser.id == OrderServiceUser.service_user_id)
      .filter(ServiceUser.user_id == id)
      .count()
    )
  }

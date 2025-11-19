from flask import Blueprint, request

from ..users import query_users
from ...database.enum import UserRole, OrderType
from ..users.session import flask_session_authentication
from ...database.schema import Service, ServiceUser, User
from database_api.operations import create, update, get_by_id, delete
from .queries import query_services, query_service_user, format_query_result, format_service_user


service_bp = Blueprint('service_bp', __name__)


@service_bp.route('', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def create_service(user: User):
  request.json['type'] = OrderType.get_enum_option(request.json['type'])
  return {'status': 'ok', 'service': create(Service, request.json).to_dict()}


@service_bp.route('', methods=['GET'])
@flask_session_authentication([UserRole.CUSTOMER, UserRole.ADMIN, UserRole.DELIVERY, UserRole.OPERATOR])
def get_services(user: User):
  services = []
  for tupla in query_services(user):
    services = format_query_result(tupla, services)
  return {'status': 'ok', 'services': services}


@service_bp.route('<id>', methods=['PUT'])
@flask_session_authentication([UserRole.ADMIN])
def update_service(user: User, id):
  service: Service = get_by_id(Service, int(id))
  request.json['type'] = OrderType.get_enum_option(request.json['type'])
  return {'status': 'ok', 'order': update(service, request.json).to_dict()}


@service_bp.route('<id>', methods=['DELETE'])
@flask_session_authentication([UserRole.ADMIN])
def delete_service(user: User, id):
  delete(get_by_id(Service, int(id)))
  return {'status': 'ok', 'message': 'Operazione completata'}


@service_bp.route('customer', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def create_service_user(user: User):
  if query_service_user(request.json['service_id'], request.json['user_id']):
    return {'status': 'ko', 'error': 'Utente già associato al servivizio'}

  service_user: ServiceUser = create(ServiceUser, request.json)
  return {
    'status': 'ok',
    'service_user': format_service_user(service_user, get_by_id(User, service_user.user_id)),
  }


@service_bp.route('customer/<id>', methods=['PUT'])
@flask_session_authentication([UserRole.ADMIN])
def update_service_user(user: User, id):
  service_user: ServiceUser = update(get_by_id(ServiceUser, int(id)), request.json)
  return {
    'status': 'ok',
    'service_user': format_service_user(service_user, get_by_id(User, service_user.user_id)),
  }


@service_bp.route('customer/<id>', methods=['DELETE'])
@flask_session_authentication([UserRole.ADMIN])
def delete_service_user(user: User, id):
  delete(get_by_id(ServiceUser, int(id)))
  return {'status': 'ok', 'message': 'Operazione completata'}


@service_bp.route('set-all-users', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN])
def set_all_users(user: User):
  service: Service = get_by_id(Service, int(request.args['service_id']))
  users = query_users(user, UserRole.CUSTOMER)
  before_service_users_ids = [user.id for user in query_service_user(service.id)]
  service_users = []
  for user in users:
    if user.id not in before_service_users_ids:
      service_users.append(
        format_service_user(
          create(ServiceUser, {'user_id': user.id, 'service_id': service.id, 'price': float(request.args['price'])}),
          user,
        )
      )
  return {'status': 'ok', 'service_users': service_users}

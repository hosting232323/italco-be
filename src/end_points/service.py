from flask import Blueprint, request

from .users import query_users
from database_api import Session
from api import error_catching_decorator
from . import flask_session_authentication
from ..database.enum import UserRole, OrderType
from ..database.schema import Service, ServiceUser, ItalcoUser
from database_api.operations import create, update, get_by_id, delete


service_bp = Blueprint('service_bp', __name__)


@service_bp.route('', methods=['POST'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN])
def create_service(user: ItalcoUser):
  request.json['type'] = OrderType.get_enum_option(request.json['type'])
  return {
    'status': 'ok',
    'service': create(Service, request.json).to_dict()
  }


@service_bp.route('', methods=['GET'])
@error_catching_decorator
@flask_session_authentication([UserRole.CUSTOMER, UserRole.ADMIN, UserRole.DELIVERY, UserRole.OPERATOR])
def get_services(user: ItalcoUser):
  services = []
  for tupla in query_services(user):
    services = format_query_result(tupla, services)
  return {
    'status': 'ok',
    'services': services
  }


@service_bp.route('<id>', methods=['PUT'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN])
def update_service(user: ItalcoUser, id):
  service: Service = get_by_id(Service, int(id))
  request.json['type'] = OrderType.get_enum_option(request.json['type'])
  return {
    'status': 'ok',
    'order': update(service, request.json).to_dict()
  }


@service_bp.route('<id>', methods=['DELETE'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN])
def delete_service(user: ItalcoUser, id):
  delete(get_by_id(Service, int(id)))
  return {
    'status': 'ok',
    'message': 'Operazione completata'
  }


@service_bp.route('customer', methods=['POST'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN])
def create_service_user(user: ItalcoUser):
  if query_service_user(
    request.json['service_id'], request.json['user_id']
  ):
    return {
      'status': 'ko',
      'error': 'Utente già associato al servivizio'
    }

  service_user = create(ServiceUser, request.json)
  return {
    'status': 'ok',
    'service_user': format_service_user(
      service_user, get_by_id(ItalcoUser, service_user.user_id)
    )
  }


@service_bp.route('customer/<id>', methods=['DELETE'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN])
def delete_service_user(user: ItalcoUser, id):
  delete(get_by_id(ServiceUser, int(id)))
  return {
    'status': 'ok',
    'message': 'Operazione completata'
  }


@service_bp.route('set-all-users', methods=['GET'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN])
def set_all_users(user: ItalcoUser):
  service: Service = get_by_id(Service, int(request.args['service_id']))
  users = query_users(user, UserRole.CUSTOMER)
  before_service_users_ids = [user.id for user in query_service_user(service.id)]
  service_users = []
  for user in users:
    if not user.id in before_service_users_ids:
      service_users.append(format_service_user(create(ServiceUser, {
        'user_id': user.id,
        'service_id': service.id,
        'price': float(request.args['price'])
      }), user))
  return {
    'status': 'ok',
    'service_users': service_users
  }


def query_services(user: ItalcoUser = None) -> list[tuple[Service, ServiceUser, ItalcoUser]]:
  with Session() as session:
    query = session.query(Service, ServiceUser, ItalcoUser).outerjoin(
      ServiceUser, ServiceUser.service_id == Service.id
    ).outerjoin(
      ItalcoUser, ItalcoUser.id == ServiceUser.user_id
    )
    if user.role == UserRole.CUSTOMER:
      query = query.filter(
        ServiceUser.user_id == user.id
      )
    return query.all()


def query_service_user(service_id: int, user_id: int = None) -> list[ServiceUser]|ServiceUser:
  with Session() as session:
    query = session.query(ServiceUser).filter(
      ServiceUser.service_id == service_id
    )
    if user_id:
      query = query.filter(
        ServiceUser.user_id == user_id
      )
    return query.all() if not user_id else query.first()


def format_query_result(tupla: tuple[Service, ServiceUser, ItalcoUser], list: list[dict]) -> list[dict]:
  for element in list:
    if element['id'] == tupla[0].id:
      if tupla[1] and tupla[2]:
        element['users'].append(format_service_user(tupla[1], tupla[2]))
      return list

  output = tupla[0].to_dict()
  output['users'] = []
  if tupla[1] and tupla[2]:
    output['users'].append(format_service_user(tupla[1], tupla[2]))
  list.append(output)
  return list


def format_service_user(service_user: ServiceUser, user: ItalcoUser) -> dict:
  output = service_user.to_dict()
  output['email'] = user.email
  return output

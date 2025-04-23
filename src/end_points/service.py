from flask import Blueprint, request

from database_api import Session
from . import error_catching_decorator
from ..database.schema import Service, ServiceUser
from database_api.operations import create, update, get_by_id, delete


service_bp = Blueprint('service_bp', __name__)


@service_bp.route('', methods=['POST'])
@error_catching_decorator
def create_service():
  return {
    'status': 'ok',
    'service': create(Service, request.json).to_dict()
  }


@service_bp.route('', methods=['GET'])
@error_catching_decorator
def get_services():
  services = []
  for tupla in query_services():
    services = format_query_result(tupla, services)
  return {
    'status': 'ok',
    'services': services
  }


@service_bp.route('<id>', methods=['PUT'])
@error_catching_decorator
def update_service(id):
  service: Service = get_by_id(Service, int(id))
  return {
    'status': 'ok',
    'order': update(service, request.json).to_dict()
  }


@service_bp.route('<id>', methods=['DELETE'])
@error_catching_decorator
def delete_service(id):
  delete(get_by_id(Service, int(id)))
  return {
    'status': 'ok',
    'message': 'Operazione completata'
  }


@service_bp.route('customer', methods=['POST'])
@error_catching_decorator
def create_service_user():
  return {
    'status': 'ok',
    'service_user': create(ServiceUser, request.json).to_dict()
  }


@service_bp.route('customer/<id>', methods=['DELETE'])
@error_catching_decorator
def delete_service_user(id):
  delete(get_by_id(ServiceUser, int(id)))
  return {
    'status': 'ok',
    'message': 'Operazione completata'
  }


def query_services() -> list[tuple[Service, ServiceUser]]:
  with Session() as session:
    query = session.query(Service, ServiceUser).outerjoin(
      ServiceUser, ServiceUser.service_id == Service.id
    )
    if 'customer_id' in request.args:
      query = query.filter(
        ServiceUser.user_id == request.args['customer_id']
      )
    return query.all()


def format_query_result(tupla: tuple[Service, ServiceUser], list: list[dict]) -> list[dict]:
  for element in list:
    if element['id'] == tupla[0].id:
      element['users'].append(tupla[1].to_dict())
      return list

  output = tupla[0].to_dict()
  output['users'] = [tupla[1].to_dict()]
  list.append(output)
  return list

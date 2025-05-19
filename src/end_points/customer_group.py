from flask import Blueprint, request

from database_api import Session
from ..database.enum import UserRole
from ..database.schema import CustomerGroup, ItalcoUser
from . import error_catching_decorator, flask_session_authentication
from database_api.operations import create, delete, get_by_id, update


customer_group_bp = Blueprint('customer_group_bp', __name__)


@customer_group_bp.route('user', methods=['PATCH'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN])
def assign_customer_group_user(user: ItalcoUser):
  customer_user: ItalcoUser = get_by_id(ItalcoUser, request.json['user_id'])
  update(customer_user, {
    'customer_group_id': request.json['customer_group_id']
  })
  return {
    'status': 'ok',
    'user': customer_user.format_user(user.role)
  }


@customer_group_bp.route('', methods=['POST'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN])
def create_customer_group(user: ItalcoUser):
  return {
    'status': 'ok',
    'customer_group': create(CustomerGroup, request.json).to_dict()
  }


@customer_group_bp.route('<id>', methods=['DELETE'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN])
def delete_customer_group(user: ItalcoUser, id):
  delete(get_by_id(CustomerGroup, int(id)))
  return {
    'status': 'ok',
    'message': 'Operazione completata'
  }


@customer_group_bp.route('', methods=['GET'])
@error_catching_decorator
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN, UserRole.DELIVERY, UserRole.CUSTOMER])
def get_customer_groups(user: ItalcoUser):
  customer_groups = []
  for tupla in query_customer_groups():
    customer_groups = format_query_result(tupla, customer_groups, user.role)
  return {
    'status': 'ok',
    'customer_groups': customer_groups
  }


def format_query_result(tupla: tuple[CustomerGroup, ItalcoUser], list: list[dict], role: UserRole) -> list[dict]:
  for element in list:
    if element['id'] == tupla[0].id:
      if tupla[1]:
        element['users'].append(tupla[1].format_user(role))
      return list

  output = tupla[0].to_dict()
  output['users'] = []
  if tupla[1]:
    output['users'].append(tupla[1].format_user(role))
  list.append(output)
  return list


def query_customer_groups() -> list[tuple[CustomerGroup, ItalcoUser]]:
  with Session() as session:
    return session.query(CustomerGroup, ItalcoUser).outerjoin(
      ItalcoUser, CustomerGroup.id == ItalcoUser.customer_group_id
    ).all()

from flask import Blueprint, request

from database_api import Session
from ..database.enum import UserRole
from ..database.schema import DeliveryGroup, ItalcoUser
from . import error_catching_decorator, flask_session_authentication
from database_api.operations import create, delete, get_by_id, update


delivery_group_bp = Blueprint('delivery_group_bp', __name__)


@delivery_group_bp.route('user', methods=['PATCH'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN])
def assign_delivery_group_user(user: ItalcoUser):
  user: ItalcoUser = get_by_id(ItalcoUser, request.json['user_id'])
  update(user, {
    'delivery_group_id': request.json['delivery_group_id']
  })
  return {
    'status': 'ok',
    'user': format_user(user)
  }


@delivery_group_bp.route('', methods=['POST'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN])
def create_delivery_group(user: ItalcoUser):
  return {
    'status': 'ok',
    'delivery_group': create(DeliveryGroup, request.json).to_dict()
  }


@delivery_group_bp.route('<id>', methods=['DELETE'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN])
def delete_delivery_group(user: ItalcoUser, id):
  delete(get_by_id(DeliveryGroup, int(id)))
  return {
    'status': 'ok',
    'message': 'Operazione completata'
  }


@delivery_group_bp.route('', methods=['GET'])
@error_catching_decorator
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN])
def get_delivery_groups(user: ItalcoUser):
  delivery_groups = []
  for tupla in query_delivery_groups():
    delivery_groups = format_query_result(tupla, delivery_groups)
  return {
    'status': 'ok',
    'delivery_groups': delivery_groups
  }


def format_query_result(tupla: tuple[DeliveryGroup, ItalcoUser], list: list[dict]) -> list[dict]:
  for element in list:
    if element['id'] == tupla[0].id:
      if tupla[1]:
        element['users'].append(format_user(tupla[1]))
      return list

  output = tupla[0].to_dict()
  output['users'] = []
  if tupla[1]:
    output['users'].append(format_user(tupla[1]))
  list.append(output)
  return list


def query_delivery_groups() -> list[tuple[DeliveryGroup, ItalcoUser]]:
  with Session() as session:
    return session.query(DeliveryGroup, ItalcoUser).outerjoin(
      ItalcoUser, DeliveryGroup.id == ItalcoUser.delivery_group_id
    ).all()


def format_user(user: ItalcoUser) -> dict:
  return {
    'id': user.id,
    'email': user.email
  }

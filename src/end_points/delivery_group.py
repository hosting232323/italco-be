from flask import Blueprint, request

from database_api import Session
from ..database.enum import UserRole
from . import flask_session_authentication
from ..database.schema import DeliveryGroup, ItalcoUser
from database_api.operations import create, delete, get_by_id, update

delivery_group_bp = Blueprint('delivery_group_bp', __name__)


@delivery_group_bp.route('user', methods=['PATCH'])
@flask_session_authentication([UserRole.ADMIN])
def assign_delivery_group_user(user: ItalcoUser):
  delivery_user: ItalcoUser = get_by_id(ItalcoUser, request.json['user_id'])
  update(delivery_user, {'delivery_group_id': request.json['delivery_group_id']})
  return {'status': 'ok', 'user': delivery_user.format_user(user.role)}


@delivery_group_bp.route('', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def create_delivery_group(user: ItalcoUser):
  return {'status': 'ok', 'delivery_group': create(DeliveryGroup, request.json).to_dict()}


@delivery_group_bp.route('<id>', methods=['DELETE'])
@flask_session_authentication([UserRole.ADMIN])
def delete_delivery_group(user: ItalcoUser, id):
  delete(get_by_id(DeliveryGroup, int(id)))
  return {'status': 'ok', 'message': 'Operazione completata'}


@delivery_group_bp.route('', methods=['GET'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN, UserRole.DELIVERY, UserRole.CUSTOMER])
def get_delivery_groups(user: ItalcoUser):
  delivery_groups = []
  for tupla in query_delivery_groups():
    delivery_groups = format_query_result(tupla, delivery_groups, user.role)
  return {'status': 'ok', 'delivery_groups': delivery_groups}


def format_query_result(tupla: tuple[DeliveryGroup, ItalcoUser], list: list[dict], role: UserRole) -> list[dict]:
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


def query_delivery_groups() -> list[tuple[DeliveryGroup, ItalcoUser]]:
  with Session() as session:
    return (
      session.query(DeliveryGroup, ItalcoUser)
      .outerjoin(ItalcoUser, DeliveryGroup.id == ItalcoUser.delivery_group_id)
      .all()
    )

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
def create_delivery_group_user(user: ItalcoUser):
  update(get_by_id(ItalcoUser, request.json['user_id']), {
    'delivery_group_id': request.json['delivery_group_id']
  })
  return {
    'status': 'ok',
    'message': 'Operazione completata'
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
  return {
    'status': 'ok',
    'delivery_groups': [delivery_group.to_dict() for delivery_group in query_delivery_groups()]
  }


def query_delivery_groups() -> list[DeliveryGroup]:
  with Session() as session:
    return session.query(DeliveryGroup).all()

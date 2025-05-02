from flask import Blueprint, request

from database_api import Session
from ..database.enum import UserRole
from ..database.schema import Addressee, ItalcoUser
from . import error_catching_decorator, flask_session_authentication
from database_api.operations import create, delete, get_by_id, update


addressee_bp = Blueprint('addressee_bp', __name__)


@addressee_bp.route('', methods=['POST'])
@error_catching_decorator
@flask_session_authentication([UserRole.CUSTOMER])
def create_addressee(user: ItalcoUser):
  request.json['user_id'] = user.id
  return {
    'status': 'ok',
    'addressee': create(Addressee, request.json).to_dict()
  }


@addressee_bp.route('<id>', methods=['DELETE'])
@error_catching_decorator
@flask_session_authentication([UserRole.CUSTOMER])
def delete_addressee(user: ItalcoUser, id):
  delete(get_by_id(Addressee, int(id)))
  return {
    'status': 'ok',
    'message': 'Operazione completata'
  }


@addressee_bp.route('', methods=['GET'])
@error_catching_decorator
@flask_session_authentication([UserRole.CUSTOMER, UserRole.ADMIN, UserRole.OPERATOR, UserRole.DELIVERY])
def get_addressees(user: ItalcoUser):
  return {
    'status': 'ok',
    'addressees': query_addressees(user)
  }


@addressee_bp.route('<id>', methods=['PUT'])
@error_catching_decorator
@flask_session_authentication([UserRole.CUSTOMER])
def update_addressee(user: ItalcoUser, id):
  addressee: Addressee = get_by_id(Addressee, int(id))
  return {
    'status': 'ok',
    'order': update(addressee, request.json).to_dict()
  }


def query_addressees(user: ItalcoUser) -> list[dict]:
  with Session() as session:
    if user.role == UserRole.CUSTOMER:
      return [addressee.to_dict() for addressee in session.query(Addressee).filter(
        Addressee.user_id == user.id
      ).all()]
    else:
      return [{
        **tupla[0].to_dict(),
        'name': f'{tupla[0].name} ({tupla[1].email})'
      } for tupla in session.query(Addressee, ItalcoUser).outerjoin(
        ItalcoUser, Addressee.user_id == ItalcoUser.id
      ).all()]

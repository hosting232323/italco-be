from flask import Blueprint, request

from database_api import Session
from ..database.enum import UserRole
from ..database.schema import Addressee, ItalcoUser
from database_api.operations import create, delete, get_by_id
from . import error_catching_decorator, flask_session_authentication


addressee_bp = Blueprint('addressee_bp', __name__)


@addressee_bp.route('', methods=['POST'])
@error_catching_decorator
@flask_session_authentication([UserRole.CUSTOMER])
def create_addressee(user: ItalcoUser):
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
@flask_session_authentication([UserRole.CUSTOMER, UserRole.ADMIN])
def get_addressees(user: ItalcoUser):
  return {
    'status': 'ok',
    'addressees': [addressee.to_dict() for addressee in query_addressees(user)]
  }


def query_addressees(user: ItalcoUser) -> list[Addressee]:
  with Session() as session:
    return session.query(Addressee).filter(
      Addressee.user_id == user.id
    ).all()

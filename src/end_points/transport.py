from flask import Blueprint, request

from database_api import Session
from ..database.enum import UserRole
from ..database.schema import Transport, User
from .users.session import flask_session_authentication
from database_api.operations import create, delete, get_by_id, update


transport_bp = Blueprint('transport_bp', __name__)


@transport_bp.route('', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def create_transport(user: User):
  return {'status': 'ok', 'transport': create(Transport, request.json).to_dict()}


@transport_bp.route('<id>', methods=['DELETE'])
@flask_session_authentication([UserRole.ADMIN])
def delete_transport(user: User, id):
  delete(get_by_id(Transport, int(id)))
  return {'status': 'ok', 'message': 'Operazione completata'}


@transport_bp.route('', methods=['GET'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN])
def get_transports(user: User):
  return {'status': 'ok', 'transports': [transport.to_dict() for transport in query_transports()]}


@transport_bp.route('<id>', methods=['PUT'])
@flask_session_authentication([UserRole.ADMIN])
def update_transport(user: User, id):
  transport: Transport = get_by_id(Transport, int(id))
  return {'status': 'ok', 'order': update(transport, request.json).to_dict()}


def query_transports() -> list[Transport]:
  with Session() as session:
    return session.query(Transport).all()

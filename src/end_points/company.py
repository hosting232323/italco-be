from flask import Blueprint, request

from database_api import Session
from ..database.enum import UserRole
from ..database.schema import Company, User
from .users.session import flask_session_authentication
from database_api.operations import create, delete, get_by_id, update


company_bp = Blueprint('company_bp', __name__)


@company_bp.route('', methods=['POST'])
@flask_session_authentication([UserRole.SUPER_ADMIN])
def create_company(user: User):
  create(Company, request.json)
  return {'status': 'ok', 'message': 'Operazione effettuata'}


@company_bp.route('', methods=['GET'])
@flask_session_authentication([UserRole.SUPER_ADMIN])
def get_companies(user: User):
  return {'status': 'ok', 'companies': [c.to_dict() for c in query_all_companies()]}


def query_all_companies() -> list[Company]:
  with Session() as session:
    return session.query(Company).all()

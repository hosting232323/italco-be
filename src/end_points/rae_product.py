from flask import Blueprint, request

from database_api import Session
from ..database.enum import UserRole
from ..database.schema import RaeProduct, User
from .users.session import flask_session_authentication
from database_api.operations import create, delete, get_by_id, update


rae_product_bp = Blueprint('rae_product_bp', __name__)


@rae_product_bp.route('', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def create_rae_product(user: User):
  return {'status': 'ok', 'rae_product': create(RaeProduct, request.json).to_dict()}


@rae_product_bp.route('<id>', methods=['DELETE'])
@flask_session_authentication([UserRole.ADMIN])
def delete_rae_product(user: User, id):
  delete(get_by_id(RaeProduct, int(id)))
  return {'status': 'ok', 'message': 'Operazione completata'}


@rae_product_bp.route('', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.CUSTOMER, UserRole.OPERATOR])
def get_rae_products(user: User):
  return {
    'status': 'ok',
    'rae_products': [rae_product.to_dict() for rae_product in query_rae_products()],
  }


@rae_product_bp.route('<id>', methods=['PUT'])
@flask_session_authentication([UserRole.ADMIN])
def update_rae_product(user: User, id):
  rae_product: RaeProduct = get_by_id(RaeProduct, int(id))
  return {'status': 'ok', 'order': update(rae_product, request.json).to_dict()}


def query_rae_products() -> list[RaeProduct]:
  with Session() as session:
    return session.query(RaeProduct).all()

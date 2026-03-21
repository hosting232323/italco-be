from datetime import date
from flask import Blueprint, request
from sqlalchemy import extract, func, and_

from database_api import Session
from ..database.enum import UserRole
from .users.session import flask_session_authentication
from ..database.schema import RaeProduct, User, Product, ServiceUser
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


def query_count_rae_products(product_id: int, user_id: int) -> int:
  product: Product = get_by_id(Product, product_id)
  if not product:
    return 0

  with Session() as session:
    return (
      session.query(func.count(Product.id))
      .join(
        ServiceUser,
        and_(
          ServiceUser.id == Product.service_user_id,
          ServiceUser.user_id == user_id,
          Product.rae_product_id.isnot(None),
          Product.created_at <= product.created_at,
          extract('year', Product.created_at) == date.today().year,
        ),
      )
      .scalar()
    )

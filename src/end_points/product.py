from flask import Blueprint, request

from database_api import Session
from ..database.enum import UserRole
from ..database.schema import Product, ItalcoUser
from . import error_catching_decorator, flask_session_authentication
from database_api.operations import create, delete, get_by_id, update


product_bp = Blueprint('product_bp', __name__)


@product_bp.route('', methods=['POST'])
@error_catching_decorator
@flask_session_authentication([UserRole.CUSTOMER])
def create_product(user: ItalcoUser):
  request.json['user_id'] = user.id
  return {
    'status': 'ok',
    'product': create(Product, request.json).to_dict()
  }


@product_bp.route('<id>', methods=['DELETE'])
@error_catching_decorator
@flask_session_authentication([UserRole.CUSTOMER])
def delete_product(user: ItalcoUser, id):
  delete(get_by_id(Product, int(id)))
  return {
    'status': 'ok',
    'message': 'Operazione completata'
  }


@product_bp.route('', methods=['GET'])
@error_catching_decorator
@flask_session_authentication([UserRole.CUSTOMER, UserRole.ADMIN, UserRole.OPERATOR, UserRole.DELIVERY])
def get_products(user: ItalcoUser):
  return {
    'status': 'ok',
    'products': [product.to_dict() for product in query_products(user)]
  }


@product_bp.route('<id>', methods=['PUT'])
@error_catching_decorator
@flask_session_authentication([UserRole.CUSTOMER])
def update_product(user: ItalcoUser, id):
  product: Product = get_by_id(Product, int(id))
  return {
    'status': 'ok',
    'order': update(product, request.json).to_dict()
  }


def query_products(user: ItalcoUser) -> list[Product]:
  with Session() as session:
    query = session.query(Product)
    if user.role == UserRole.CUSTOMER:
      query = query.filter(
        Product.user_id == user.id
      )
    return query.all()

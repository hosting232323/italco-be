from flask import Blueprint, request


from ...database.schema import User
from ...database.enum import UserRole
from .product import get_rae_products
from ..users.session import flask_session_authentication
from .product_group import (
  create_rae_product_group,
  delete_rae_product_group,
  update_rae_product_group,
  get_rae_product_groups,
)


rae_bp = Blueprint('rae_bp', __name__)


@rae_bp.route('product-group', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def create_product_group(user: User):
  return create_rae_product_group(request.json)


@rae_bp.route('product-group/<id>', methods=['DELETE'])
@flask_session_authentication([UserRole.ADMIN])
def delete_product_group(user: User, id):
  return delete_rae_product_group(int(id))


@rae_bp.route('product-group', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
def get_product_groups(user: User):
  return get_rae_product_groups()


@rae_bp.route('product-group/<id>', methods=['PUT'])
@flask_session_authentication([UserRole.ADMIN])
def update_product_group(user: User, id):
  return update_rae_product_group(int(id), request.json)


@rae_bp.route('product', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
def get_products(user: User):
  return get_rae_products()

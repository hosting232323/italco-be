import json
from flask import Blueprint, request

from ...database.schema import User
from ...database.enum import UserRole
from .document import handle_document
from api.storage.utils import serve_file
from api import error_catching_decorator
from ..users.session import flask_session_authentication
from .product import get_rae_products, update_rae_product
from .product_group import (
  create_rae_product_group,
  delete_rae_product_group,
  update_rae_product_group,
  get_rae_product_groups,
)


rae_bp = Blueprint('rae_bp', __name__)


@rae_bp.route('product-group', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def create_product_group(_):
  return create_rae_product_group(request.json)


@rae_bp.route('product-group/<id>', methods=['DELETE'])
@flask_session_authentication([UserRole.ADMIN])
def delete_product_group(_, id):
  return delete_rae_product_group(int(id))


@rae_bp.route('product-group', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
def get_product_groups(_):
  return get_rae_product_groups()


@rae_bp.route('product-group/<id>', methods=['PUT'])
@flask_session_authentication([UserRole.ADMIN])
def update_product_group(_, id):
  return update_rae_product_group(int(id), request.json)


@rae_bp.route('product/filter', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
def get_products(user: User):
  return get_rae_products(user, request.json['filters'])


@rae_bp.route('product/<id>', methods=['PUT'])
@flask_session_authentication([UserRole.ADMIN])
def update_product(_, id):
  return update_rae_product(int(id), handle_document(json.loads(request.form.get('data'))))


@rae_bp.route('dtr-documents/<filename>', methods=['GET'])
@error_catching_decorator
def serve_image_endpoint(filename):
  return serve_file(filename, 'dtr-documents')

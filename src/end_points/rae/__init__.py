import json
from flask import Blueprint, request

from ...database.schema import User
from ...utils.file import serve_file
from ...database.enum import UserRole
from .document import handle_document
from api import error_catching_decorator
from ..users.session import flask_session_authentication
from .product import get_rae_products, update_rae_product
from .disposal import create_rae_disposal, get_rae_disposals, update_rae_disposal
from .carrier import create_rae_carrier, update_rae_carrier, delete_rae_carrier, get_rae_carriers
from .product_group import (
  create_rae_product_group,
  delete_rae_product_group,
  update_rae_product_group,
  get_rae_product_groups,
)
from .collection_center import (
  create_rae_collection_center,
  update_rae_collection_center,
  delete_rae_collection_center,
  get_rae_collection_centers,
)


rae_bp = Blueprint('rae_bp', __name__)


@rae_bp.route('product-group', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
@error_catching_decorator
def create_product_group(_):
  return create_rae_product_group(request.json)


@rae_bp.route('product-group/<id>', methods=['DELETE'])
@flask_session_authentication([UserRole.ADMIN])
@error_catching_decorator
def delete_product_group(_, id):
  return delete_rae_product_group(int(id))


@rae_bp.route('product-group', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
@error_catching_decorator
def get_product_groups(_):
  return get_rae_product_groups()


@rae_bp.route('product-group/<id>', methods=['PUT'])
@flask_session_authentication([UserRole.ADMIN])
@error_catching_decorator
def update_product_group(_, id):
  return update_rae_product_group(int(id), request.json)


@rae_bp.route('product/filter', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
@error_catching_decorator
def get_products(user: User):
  return get_rae_products(user, request.json['filters'])


@rae_bp.route('product/<id>', methods=['PUT'])
@flask_session_authentication([UserRole.ADMIN])
@error_catching_decorator
def update_product(_, id):
  return update_rae_product(
    int(id), handle_document(json.loads(request.form.get('data')), 'rae/dtr-documents', 'rae_product', 'link')
  )


@rae_bp.route('<folder>/<filename>', methods=['GET'])
@error_catching_decorator
def serve_dtr_endpoint(folder, filename):
  if folder not in ['dtr-documents', 'fir-documents']:
    return {'status': 'ok', 'error': 'Invalid folder'}

  return serve_file(filename, folder)


@rae_bp.route('carrier', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
@error_catching_decorator
def create_carrier(_):
  return create_rae_carrier(request.json)


@rae_bp.route('carrier', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
@error_catching_decorator
def get_carriers(_):
  return get_rae_carriers()


@rae_bp.route('carrier/<id>', methods=['PUT'])
@flask_session_authentication([UserRole.ADMIN])
@error_catching_decorator
def update_carrier(_, id):
  return update_rae_carrier(int(id), request.json)


@rae_bp.route('carrier/<id>', methods=['DELETE'])
@flask_session_authentication([UserRole.ADMIN])
@error_catching_decorator
def delete_carrier(_, id):
  return delete_rae_carrier(int(id))


@rae_bp.route('collection-center', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
@error_catching_decorator
def create_collection_center(_):
  return create_rae_collection_center(request.json)


@rae_bp.route('collection-center', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
@error_catching_decorator
def get_collection_center(_):
  return get_rae_collection_centers()


@rae_bp.route('collection-center/<id>', methods=['PUT'])
@flask_session_authentication([UserRole.ADMIN])
@error_catching_decorator
def update_collection_center(_, id):
  return update_rae_collection_center(int(id), request.json)


@rae_bp.route('collection-center/<id>', methods=['DELETE'])
@flask_session_authentication([UserRole.ADMIN])
@error_catching_decorator
def delete_collection_center(_, id):
  return delete_rae_collection_center(int(id))


@rae_bp.route('disposal', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
@error_catching_decorator
def create_disposal(_):
  return create_rae_disposal(request.json)


@rae_bp.route('disposal', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
@error_catching_decorator
def get_disposal(_):
  return get_rae_disposals()


@rae_bp.route('disposal/<id>', methods=['PUT'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
@error_catching_decorator
def update_disposal(_, id):
  return update_rae_disposal(
    int(id), handle_document(json.loads(request.form.get('data')), 'rae/fir-documents', 'disposal', 'document_fir')
  )

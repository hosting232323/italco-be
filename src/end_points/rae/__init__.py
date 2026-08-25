import json
from flask import Blueprint, request, send_from_directory

from api.storage import get_full_path
from api.storage.files import validate_files, PDF_EXTENSIONS

from ... import STATIC_FOLDER
from ...database.schema import User
from ...database.enum import UserRole
from .product import get_rae_products, update_rae_product
from .. import flask_session_authentication
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
@flask_session_authentication([UserRole.ADMIN], rae_required=True)
def create_product_group(_):
  return create_rae_product_group(request.json)


@rae_bp.route('product-group/<id>', methods=['DELETE'])
@flask_session_authentication([UserRole.ADMIN], rae_required=True)
def delete_product_group(_, id):
  return delete_rae_product_group(int(id))


@rae_bp.route('product-group', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR], rae_required=True)
def get_product_groups(_):
  return get_rae_product_groups()


@rae_bp.route('product-group/<id>', methods=['PUT'])
@flask_session_authentication([UserRole.ADMIN], rae_required=True)
def update_product_group(_, id):
  return update_rae_product_group(int(id), request.json)


@rae_bp.route('product/filter', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR], rae_required=True)
def get_products(user: User):
  return get_rae_products(user, request.json['filters'])


@rae_bp.route('product/<id>', methods=['PUT'])
@flask_session_authentication([UserRole.ADMIN], rae_required=True)
def update_product(_, id):
  error = validate_files(request.files.values(), PDF_EXTENSIONS)
  if error:
    return {'status': 'ko', 'message': error}

  return update_rae_product(int(id), json.loads(request.form.get('data')), request.files)


@rae_bp.route('carrier', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN], rae_required=True)
def create_carrier(_):
  return create_rae_carrier(request.json)


@rae_bp.route('carrier', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR], rae_required=True)
def get_carriers(_):
  return get_rae_carriers()


@rae_bp.route('carrier/<id>', methods=['PUT'])
@flask_session_authentication([UserRole.ADMIN], rae_required=True)
def update_carrier(_, id):
  return update_rae_carrier(int(id), request.json)


@rae_bp.route('carrier/<id>', methods=['DELETE'])
@flask_session_authentication([UserRole.ADMIN], rae_required=True)
def delete_carrier(_, id):
  return delete_rae_carrier(int(id))


@rae_bp.route('collection-center', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN], rae_required=True)
def create_collection_center(_):
  return create_rae_collection_center(request.json)


@rae_bp.route('collection-center', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR], rae_required=True)
def get_collection_center(_):
  return get_rae_collection_centers()


@rae_bp.route('collection-center/<id>', methods=['PUT'])
@flask_session_authentication([UserRole.ADMIN], rae_required=True)
def update_collection_center(_, id):
  return update_rae_collection_center(int(id), request.json)


@rae_bp.route('collection-center/<id>', methods=['DELETE'])
@flask_session_authentication([UserRole.ADMIN], rae_required=True)
def delete_collection_center(_, id):
  return delete_rae_collection_center(int(id))


@rae_bp.route('disposal', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR], rae_required=True)
def create_disposal(_):
  return create_rae_disposal(request.json)


@rae_bp.route('disposal', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR], rae_required=True)
def get_disposal(_):
  return get_rae_disposals()


@rae_bp.route('disposal/<id>', methods=['PUT'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR], rae_required=True)
def update_disposal(_, id):
  error = validate_files(request.files.values(), PDF_EXTENSIONS)
  if error:
    return {'status': 'ko', 'message': error}

  return update_rae_disposal(int(id), json.loads(request.form.get('data')), request.files)


@rae_bp.route('<folder>/<filename>', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR], allow_query_token=True, rae_required=True)
def serve_document(_, folder, filename):
  if folder not in ['dtr-documents', 'fir-first-document', 'fir-fourth-document']:
    return {'status': 'ko', 'message': 'Invalid folder'}

  return send_from_directory(get_full_path(STATIC_FOLDER, folder), filename)

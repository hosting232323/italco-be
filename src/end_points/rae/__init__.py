import json
from flask import Blueprint, request, send_from_directory

from api.storage import get_full_path
from database_api import Session

from ... import STATIC_FOLDER
from ...utils.storage import StorageTransaction
from ...database.schema import User, DtrDocument
from ...database.enum import UserRole
from .product import get_rae_products, update_rae_product
from .document import store_document, handle_document_by_name
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
  with StorageTransaction() as storage:
    with Session() as session:
      update_rae_product(int(id), json.loads(request.form.get('data')), session=session)
      store_document(
        DtrDocument,
        'rae_product_id',
        int(id),
        'rae/dtr-documents',
        session=session,
        storage=storage,
      )
      session.commit()

  return {'status': 'ok', 'message': 'Operazione completata'}


@rae_bp.route('carrier', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def create_carrier(_):
  return create_rae_carrier(request.json)


@rae_bp.route('carrier', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
def get_carriers(_):
  return get_rae_carriers()


@rae_bp.route('carrier/<id>', methods=['PUT'])
@flask_session_authentication([UserRole.ADMIN])
def update_carrier(_, id):
  return update_rae_carrier(int(id), request.json)


@rae_bp.route('carrier/<id>', methods=['DELETE'])
@flask_session_authentication([UserRole.ADMIN])
def delete_carrier(_, id):
  return delete_rae_carrier(int(id))


@rae_bp.route('collection-center', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def create_collection_center(_):
  return create_rae_collection_center(request.json)


@rae_bp.route('collection-center', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
def get_collection_center(_):
  return get_rae_collection_centers()


@rae_bp.route('collection-center/<id>', methods=['PUT'])
@flask_session_authentication([UserRole.ADMIN])
def update_collection_center(_, id):
  return update_rae_collection_center(int(id), request.json)


@rae_bp.route('collection-center/<id>', methods=['DELETE'])
@flask_session_authentication([UserRole.ADMIN])
def delete_collection_center(_, id):
  return delete_rae_collection_center(int(id))


@rae_bp.route('disposal', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
def create_disposal(_):
  return create_rae_disposal(request.json)


@rae_bp.route('disposal', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
def get_disposal(_):
  return get_rae_disposals()


@rae_bp.route('disposal/<id>', methods=['PUT'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
def update_disposal(_, id):
  with StorageTransaction() as storage:
    with Session() as session:
      data = json.loads(request.form.get('data'))

      if 'first_copy_document_fir' in request.files:
        data = handle_document_by_name(
          data,
          'rae/fir-first-document',
          'fir_first_document',
          'first_copy_document_fir',
          session=session,
          storage=storage,
        )

      if 'fourth_copy_document_fir' in request.files:
        data = handle_document_by_name(
          data,
          'rae/fir-fourth-document',
          'fir_fourth_document',
          'fourth_copy_document_fir',
          session=session,
          storage=storage,
        )

      update_rae_disposal(int(id), data, session=session)
      session.commit()

  return {'status': 'ok', 'message': 'Operazione completata'}


@rae_bp.route('<folder>/<filename>', methods=['GET'])
def serve_document(folder, filename):
  if folder not in ['dtr-documents', 'fir-first-document', 'fir-fourth-document']:
    return {'status': 'ko', 'message': 'Invalid folder'}

  return send_from_directory(get_full_path(STATIC_FOLDER, folder, False), filename)

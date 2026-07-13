import json
from flask import Blueprint, current_app, request, send_from_directory

from ... import STATIC_FOLDER
from ...utils.storage import StorageTransaction
from .mailer import mailer_check
from database_api import Session
from .photo import handle_photos
from ...database.enum import UserRole
from api.storage import get_full_path
from ...database.schema import User, Order
from .utils import get_statuses_by_order_id
from .services import RaeProductDeletionError
from database_api.operations import get_by_id
from .api import save_order_status_to_euronics
from .. import flask_session_authentication
from api import swagger_decorator
from ..collection_point import query_collection_points_available
from .queries import get_order_photos, get_motivations_by_order_id
from .crud import create_order, update_order, filter_orders, get_order, delete_order, update_order_customer


order_bp = Blueprint('order_bp', __name__)


@order_bp.route('', methods=['POST'])
@flask_session_authentication([UserRole.CUSTOMER, UserRole.OPERATOR, UserRole.ADMIN])
def create_order_endpoint(user: User):
  return create_order(user, request.json)


@order_bp.route('filter', methods=['POST'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN, UserRole.CUSTOMER])
def filter_orders_endpoint(user: User):
  return filter_orders(request.json['filters'], user.id if user.role == UserRole.CUSTOMER else None)


@order_bp.route('external-filter', methods=['POST'])
@swagger_decorator
def external_filter_orders_endpoint():
  return filter_orders(request.json['filters'])


@order_bp.route('<id>', methods=['GET'])
def get_order_endpoint(id):
  return get_order(int(id))


@order_bp.route('<id>', methods=['PUT'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.DELIVERY, UserRole.ADMIN, UserRole.CUSTOMER])
def update_order_endpoint(user: User, id):
  try:
    with Session() as session:
      order: Order = get_by_id(Order, int(id), session=session)
      form_data = request.form.get('data')
      data = json.loads(form_data) if isinstance(form_data, str) else request.json

      if data.get('version') is not None and data['version'] != order.version:
        return {'status': 'ko', 'message': "L'ordine è stato modificato nel frattempo. Ricarica la pagina e riprova."}

      with StorageTransaction() as storage:
        if isinstance(form_data, str):
          data = handle_photos(data, order, session=session, storage=storage)

        motivation = update_order(user, order, data, session)
        session.commit()
  except RaeProductDeletionError as error:
    return {'status': 'ko', 'message': str(error)}
  except Exception:
    current_app.logger.exception('Aggiornamento ordine non completato')
    return {'status': 'ko', 'message': 'File e dati dell’ordine non sono stati salvati'}

  save_order_status_to_euronics(order)
  mailer_check(order, data, motivation)
  return {'status': 'ok', 'order': order.to_dict()}


@order_bp.route('customer', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
def update_order_customer_endpoint(user: User):
  return update_order_customer(user, request.json['user_id'], request.json['order_id'])


@order_bp.route('delivery-details/<order_id>', methods=['GET'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.CUSTOMER, UserRole.ADMIN])
def get_delivery_details(_, order_id: int):
  return {
    'status': 'ok',
    'motivations': [m.to_dict() for m in get_motivations_by_order_id(order_id)],
    'photos': [photo.link for photo in get_order_photos(order_id)],
  }


@order_bp.route('<id>', methods=['DELETE'])
@flask_session_authentication([UserRole.ADMIN])
def delete_order_endpoint(user: User, id):
  return delete_order(user, int(id))


@order_bp.route('statuses/<id>', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
def get_statuses(_, id):
  return get_statuses_by_order_id(int(id))


@order_bp.route('photos/<filename>', methods=['GET'])
def serve_image_endpoint(filename):
  return send_from_directory(get_full_path(STATIC_FOLDER, 'photos', False), filename)


@order_bp.route('collection-points/<id>', methods=['GET'])
@flask_session_authentication([UserRole.DELIVERY, UserRole.OPERATOR, UserRole.ADMIN])
def get_collection_points_available(_, id):
  return {
    'status': 'ok',
    'collection_points': [
      collection_point.to_dict() for collection_point in query_collection_points_available(int(id))
    ],
  }

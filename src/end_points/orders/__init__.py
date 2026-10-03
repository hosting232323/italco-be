import copy
import json
from flask import Blueprint, request, send_from_directory, abort, make_response
from database_api import Session

from ... import STATIC_FOLDER
from .mailer import mailer_check
from .photo import handle_photos
from .sms_sender import delay_sms_check
from ...database.enum import UserRole
from api.storage import get_full_path
from api.storage.files import validate_files, IMAGE_EXTENSIONS
from ...database.schema import User, Order, Photo
from api.storage.session import SessionWithStorage
from .utils import get_statuses_by_order_id
from ...order_integrity import lock_order_service_integrity
from database_api.operations import get_by_id
from .api import save_order_status_to_euronics
from .. import flask_session_authentication
from api import swagger_decorator
from ..collection_point import query_collection_points_available
from .queries import get_order_photos, user_can_access_order
from .move_company import list_move_targets, move_order, preview_order_move
from .crud import (
  create_order,
  update_order,
  filter_orders,
  get_order,
  get_public_order,
  delete_order,
  update_order_customer,
  restrict_order_update,
)
from .sms_sender import create_order_tracking_token


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
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN, UserRole.DELIVERY, UserRole.CUSTOMER])
def get_order_endpoint(user: User, id):
  try:
    order_id = int(id)
  except (TypeError, ValueError):
    abort(404)
  with Session() as session:
    order = session.query(Order).filter(Order.id == order_id).first()
    if not order or not user_can_access_order(user, order_id, session):
      abort(404)
  return get_order(order_id, customer_id=user.id if user.role == UserRole.CUSTOMER else None)


@order_bp.route('public', methods=['POST'])
def get_public_order_endpoint():
  token = (request.get_json(silent=True) or {}).get('token')
  if not isinstance(token, str) or len(token) > 128:
    abort(404)
  result = get_public_order(token)
  if result is None:
    abort(404)
  response = make_response(result)
  response.headers['Cache-Control'] = 'private, no-store'
  response.headers['Referrer-Policy'] = 'no-referrer'
  return response


@order_bp.route('<id>/tracking-link', methods=['POST'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN, UserRole.CUSTOMER])
def create_tracking_link_endpoint(user: User, id):
  try:
    order_id = int(id)
  except (TypeError, ValueError):
    abort(404)
  with Session() as session:
    order = session.query(Order).filter(Order.id == order_id).first()
    if not order or not user_can_access_order(user, order_id, session):
      abort(404)
    token = create_order_tracking_token(order)
  return {'status': 'ok', 'token': token}


@order_bp.route('<id>', methods=['PUT'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.DELIVERY, UserRole.ADMIN, UserRole.CUSTOMER])
def update_order_endpoint(user: User, id):
  error = validate_files(request.files.values(), IMAGE_EXTENSIONS)
  if error:
    return {'status': 'ko', 'message': error}

  with SessionWithStorage() as session:
    lock_order_service_integrity(session)
    order: Order = get_by_id(Order, int(id), session=session)
    if not user_can_access_order(user, order.id, session):
      abort(404)
    if isinstance(request.form.get('data'), str):
      data = handle_photos(json.loads(request.form.get('data')), order, session=session)
    else:
      data = copy.deepcopy(request.json)

    data = restrict_order_update(user, data, session)

    if data.get('version') is not None and data['version'] != order.version:
      return {'status': 'ko', 'message': "L'ordine è stato modificato nel frattempo. Ricarica la pagina e riprova."}
    pending_sms = []
    motivation = update_order(user, order, data, session, pending_sms=pending_sms)
    session.commit()

  save_order_status_to_euronics(order)
  mailer_check(order, data, motivation)
  for sms_order, sms_item in pending_sms:
    delay_sms_check(sms_order, sms_item)
  return {'status': 'ok', 'order': order.to_dict()}


@order_bp.route('customer', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
def update_order_customer_endpoint(user: User):
  return update_order_customer(user, request.json['user_id'], request.json['order_id'])


@order_bp.route('delivery-details/<order_id>', methods=['GET'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.CUSTOMER, UserRole.ADMIN])
def get_delivery_details(user: User, order_id: int):
  with Session() as session:
    order = session.query(Order).filter(Order.id == int(order_id)).first()
    if not order or not user_can_access_order(user, order.id, session):
      abort(404)
  return {
    'status': 'ok',
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
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR, UserRole.CUSTOMER], allow_query_token=True)
def serve_image_endpoint(user: User, filename):
  with Session() as session:
    photo = session.query(Photo).filter(Photo.link.endswith('/' + filename, autoescape=True)).first()
    if not photo or not user_can_access_order(user, photo.order_id, session):
      abort(404)
  return send_from_directory(get_full_path(STATIC_FOLDER, 'photos'), filename)


@order_bp.route('collection-points/<id>', methods=['GET'])
@flask_session_authentication([UserRole.DELIVERY, UserRole.OPERATOR, UserRole.ADMIN])
def get_collection_points_available(_, id):
  return {
    'status': 'ok',
    'collection_points': [
      collection_point.to_dict() for collection_point in query_collection_points_available(int(id))
    ],
  }


# Admin e super admin. Si opera nella company dell'ordine (quella dell'admin o
# quella selezionata dal super admin) e si sceglie la destinazione.
@order_bp.route('company-targets', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN])
def company_targets_endpoint(user: User):
  return list_move_targets()


@order_bp.route('<id>/company/preview', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def preview_order_company_endpoint(user: User, id):
  data = request.json or {}
  return preview_order_move(int(id), data.get('company_id'), data.get('user_id'))


@order_bp.route('<id>/company', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def move_order_company_endpoint(user: User, id):
  data = request.json or {}
  return move_order(int(id), data.get('company_id'), data.get('user_id'))

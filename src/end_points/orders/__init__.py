import json
from flask import Blueprint, request

from .photo import serve_image
from .mailer import mailer_check
from database_api import Session
from .photo import handle_photos
from ...database.enum import UserRole
from ...database.schema import User, Order
from .utils import get_statuses_by_order_id
from database_api.operations import get_by_id
from .api import save_order_status_to_euronics
from ..users.session import flask_session_authentication
from api import error_catching_decorator, swagger_decorator
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
@error_catching_decorator
def get_order_endpoint(id):
  return get_order(int(id))


@order_bp.route('<id>', methods=['PUT'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.DELIVERY, UserRole.ADMIN, UserRole.CUSTOMER])
def update_order_endpoint(user: User, id):
  with Session() as session:
    order: Order = get_by_id(Order, int(id), session=session)
    if isinstance(request.form.get('data'), str):
      data = handle_photos(json.loads(request.form.get('data')), order, session=session)
    else:
      data = request.json

    motivation = update_order(user, order, data, session)
    session.commit()

  save_order_status_to_euronics(order)
  mailer_check(order, data, motivation)
  return {'status': 'ok', 'order': order.to_dict()}


@order_bp.route('customer', methods=['POST'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
def update_order_customer_endpoint(user: User):
  return update_order_customer(user, request.json['user_id'], request.json['order_id'])


@order_bp.route('delivery-details/<order_id>', methods=['GET'])
@error_catching_decorator
@flask_session_authentication([UserRole.OPERATOR, UserRole.CUSTOMER, UserRole.ADMIN])
def get_delivery_details(user: User, order_id: int):
  return {
    'status': 'ok',
    'motivations': [m.to_dict() for m in get_motivations_by_order_id(order_id)],
    'photos': [photo.link for photo in get_order_photos(order_id)],
  }


@order_bp.route('<id>', methods=['DELETE'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN])
def delete_order_endpoint(user: User, id):
  return delete_order(user, int(id))


@order_bp.route('statuses/<id>', methods=['GET'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
def get_statuses(user: User, id):
  return get_statuses_by_order_id(int(id))


@order_bp.route('photos/<filename>', methods=['GET'])
@error_catching_decorator
def serve_image_endpoint(filename):
  return serve_image(filename)


@order_bp.route('collection-points/<id>', methods=['GET'])
@error_catching_decorator
@flask_session_authentication([UserRole.DELIVERY])
def get_collection_points_available(user: User, id):
  return {
    'status': 'ok',
    'collection_points': [
      collection_point.to_dict() for collection_point in query_collection_points_available(int(id))
    ],
  }

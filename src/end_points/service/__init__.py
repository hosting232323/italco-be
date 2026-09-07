from flask import Blueprint, request
from database_api import Session
from ...order_integrity import lock_order_service_integrity

from ..users import query_users
from ...database.enum import UserRole, OrderType
from .. import flask_session_authentication
from ...database.schema import Service, ServiceUser, User, Order, Product
from database_api.operations import create, update, get_by_id, delete
from .queries import query_services, query_service_user, format_query_result, format_service_user


service_bp = Blueprint('service_bp', __name__)


@service_bp.route('', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def create_service(_):
  data = {**request.json, 'type': OrderType(request.json['type'])}
  return {'status': 'ok', 'service': create(Service, data).to_dict()}


@service_bp.route('', methods=['GET'])
@flask_session_authentication([UserRole.CUSTOMER, UserRole.ADMIN, UserRole.DELIVERY, UserRole.OPERATOR])
def get_services(user: User):
  services = []
  for tupla in query_services(user):
    services = format_query_result(tupla, services)
  return {'status': 'ok', 'services': services}


@service_bp.route('<id>', methods=['PUT'])
@flask_session_authentication([UserRole.ADMIN])
def update_service(_, id):
  with Session() as session:
    lock_order_service_integrity(session)
    service = get_by_id(Service, int(id), session=session)
    data = {**request.json, 'type': OrderType(request.json['type'])}
    if data['type'] != service.type:
      incompatible = (
        session.query(Order.id)
        .join(Product, Product.order_id == Order.id)
        .join(ServiceUser, Product.service_user_id == ServiceUser.id)
        .filter(ServiceUser.service_id == service.id, Order.type != data['type'])
        .first()
      )
      if incompatible:
        return {
          'status': 'ko',
          'message': f'Tipo incompatibile con ordine {incompatible.id}: bonificare prima gli ordini.',
        }
    service = update(service, data, session=session)
    session.commit()
    return {'status': 'ok', 'order': service.to_dict()}


@service_bp.route('<id>', methods=['DELETE'])
@flask_session_authentication([UserRole.ADMIN])
def delete_service(_, id):
  delete(get_by_id(Service, int(id)))
  return {'status': 'ok', 'message': 'Operazione completata'}


@service_bp.route('customer', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def create_service_user(_):
  if query_service_user(request.json['service_id'], request.json['user_id']):
    return {'status': 'ko', 'message': 'Utente già associato al servivizio'}

  service_user: ServiceUser = create(ServiceUser, request.json)
  return {
    'status': 'ok',
    'service_user': format_service_user(service_user, get_by_id(User, service_user.user_id)),
  }


@service_bp.route('customer/<id>', methods=['PUT'])
@flask_session_authentication([UserRole.ADMIN])
def update_service_user(_, id):
  with Session() as session:
    lock_order_service_integrity(session)
    service_user = get_by_id(ServiceUser, int(id), session=session)
    # Repointing an in-use price-list row would silently change historic orders.
    changed_reference = any(
      field in request.json and int(request.json[field]) != getattr(service_user, field)
      for field in ('service_id', 'user_id', 'company_id')
    )
    if changed_reference and session.query(Product.id).filter(Product.service_user_id == service_user.id).first():
      return {'status': 'ko', 'message': 'Associazione utilizzata da ordini: creare una nuova voce di listino.'}
    service_user = update(service_user, request.json, session=session)
    session.commit()
    return {
      'status': 'ok',
      'service_user': format_service_user(service_user, get_by_id(User, service_user.user_id, session=session)),
    }


@service_bp.route('customer/<id>', methods=['DELETE'])
@flask_session_authentication([UserRole.ADMIN])
def delete_service_user(_, id):
  delete(get_by_id(ServiceUser, int(id)))
  return {'status': 'ok', 'message': 'Operazione completata'}


@service_bp.route('set-all-users', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN])
def set_all_users(user: User):
  service: Service = get_by_id(Service, int(request.args['service_id']))
  users = query_users(user, UserRole.CUSTOMER)
  before_service_users_ids = [user.id for user in query_service_user(service.id)]
  service_users = []
  for user in users:
    if user.id not in before_service_users_ids:
      service_users.append(
        format_service_user(
          create(ServiceUser, {'user_id': user.id, 'service_id': service.id, 'price': float(request.args['price'])}),
          user,
        )
      )
  return {'status': 'ok', 'service_users': service_users}

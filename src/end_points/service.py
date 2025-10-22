from flask import Blueprint, request
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

from .users import query_users
from database_api import Session
from ..database.enum import UserRole, OrderType
from .users.session import flask_session_authentication
from database_api.operations import create, update, get_by_id, delete
from ..database.schema import Service, ServiceUser, User, Order, OrderServiceUser


service_bp = Blueprint('service_bp', __name__)


@service_bp.route('', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def create_service(user: User):
  request.json['type'] = OrderType.get_enum_option(request.json['type'])
  return {'status': 'ok', 'service': create(Service, request.json).to_dict()}


@service_bp.route('', methods=['GET'])
@flask_session_authentication([UserRole.CUSTOMER, UserRole.ADMIN, UserRole.DELIVERY, UserRole.OPERATOR])
def get_services(user: User):
  services = []
  for tupla in query_services(user):
    services = format_query_result(tupla, services)
  return {'status': 'ok', 'services': services}


@service_bp.route('<id>', methods=['PUT'])
@flask_session_authentication([UserRole.ADMIN])
def update_service(user: User, id):
  service: Service = get_by_id(Service, int(id))
  request.json['type'] = OrderType.get_enum_option(request.json['type'])
  return {'status': 'ok', 'order': update(service, request.json).to_dict()}


@service_bp.route('<id>', methods=['DELETE'])
@flask_session_authentication([UserRole.ADMIN])
def delete_service(user: User, id):
  delete(get_by_id(Service, int(id)))
  return {'status': 'ok', 'message': 'Operazione completata'}


@service_bp.route('customer', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def create_service_user(user: User):
  if query_service_user(request.json['service_id'], request.json['user_id']):
    return {'status': 'ko', 'error': 'Utente già associato al servivizio'}

  service_user = create(ServiceUser, request.json)
  return {
    'status': 'ok',
    'service_user': format_service_user(service_user, get_by_id(User, service_user.user_id)),
  }


@service_bp.route('customer/<id>', methods=['DELETE'])
@flask_session_authentication([UserRole.ADMIN])
def delete_service_user(user: User, id):
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


def query_services(user: User = None) -> list[tuple[Service, ServiceUser, User]]:
  with Session() as session:
    query = (
      session.query(Service, ServiceUser, User)
      .outerjoin(ServiceUser, ServiceUser.service_id == Service.id)
      .outerjoin(User, User.id == ServiceUser.user_id)
    )
    if user.role == UserRole.CUSTOMER:
      query = query.filter(ServiceUser.user_id == user.id)
    return query.all()


def query_service_user(service_id: int, user_id: int = None) -> list[ServiceUser] | ServiceUser:
  with Session() as session:
    query = session.query(ServiceUser).filter(ServiceUser.service_id == service_id)
    if user_id:
      query = query.filter(ServiceUser.user_id == user_id)
    return query.all() if not user_id else query.first()


def format_query_result(tupla: tuple[Service, ServiceUser, User], list: list[dict]) -> list[dict]:
  for element in list:
    if element['id'] == tupla[0].id:
      if tupla[1] and tupla[2]:
        element['users'].append(format_service_user(tupla[1], tupla[2]))
      return list

  output = tupla[0].to_dict()
  output['users'] = []
  if tupla[1] and tupla[2]:
    output['users'].append(format_service_user(tupla[1], tupla[2]))
  list.append(output)
  return list


def format_service_user(service_user: ServiceUser, user: User) -> dict:
  output = service_user.to_dict()
  output['nickname'] = user.nickname
  return output


def check_services_date() -> list[datetime]:
  services_id = request.json['services_id']
  services_with_max_order = query_max_order(services_id)

  start = datetime.today().date()
  allowed_dates = []
  end = start + relativedelta(months=2)
  if not services_with_max_order:
    while start <= end:
      allowed_dates.append(start.strftime('%Y-%m-%d'))
      start += timedelta(days=1)
    return allowed_dates

  min_max_services = min(
    service.max_services for service in services_with_max_order if service.max_services is not None
  )
  orders = query_orders_in_range(services_id, start, end)
  while start <= end:
    order_count = 0
    for order in orders:
      if order.dpc == start:
        order_count += 1
    if order_count < min_max_services:
      allowed_dates.append(start.strftime('%Y-%m-%d'))
    start += timedelta(days=1)
  return allowed_dates


def query_max_order(services_id) -> list[Service]:
  with Session() as session:
    services_with_max_order = (
      session.query(Service).filter(Service.id.in_(services_id), Service.max_services.isnot(None)).all()
    )
    return services_with_max_order


def query_orders_in_range(services_id, start_date, end_date):
  with Session() as session:
    return (
      session.query(Order)
      .join(OrderServiceUser, Order.id == OrderServiceUser.order_id)
      .join(ServiceUser, ServiceUser.id == OrderServiceUser.service_user_id)
      .join(Service, Service.id == ServiceUser.service_id)
      .filter(Service.id.in_(services_id), Order.dpc >= start_date, Order.dpc <= end_date)
      .all()
    )

from datetime import datetime
from flask import Blueprint, request

from database_api import Session
from ..users.queries import format_user_with_info
from ...database.enum import UserRole, OrderStatus
from ..users.session import flask_session_authentication
from ...database.schema import Schedule, User, DeliveryGroup
from database_api.operations import create, delete, get_by_id, update
from .schedulation import assign_orders_to_groups, build_schedule_items
from ..orders.queries import query_orders, format_query_result as format_query_orders_result
from .utils import (
  handle_schedule_item,
  delete_schedule_items,
  schedule_items_updating,
  format_schedule_data,
  save_info_to_euronics,
)
from .queries import (
  query_schedules,
  query_schedules_count,
  format_query_result,
  get_delivery_groups,
  get_schedule_items,
  get_delivery_users_by_date,
  get_transports_by_date,
  get_schedule_item_for_order_id_filter,
  format_schedule_item,
)


schedule_bp = Blueprint('schedule_bp', __name__)


@schedule_bp.route('', methods=['POST'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN])
def create_schedule(user: User):
  with Session() as session:
    schedule_items, schedule_data, users, response = format_schedule_data(request.json, session=session)
    if response:
      return response

    if any(query_schedules_count(user['id'], schedule_data['date']) > 0 for user in users):
      return {'status': 'ko', 'error': 'Uno di questi utenti delivery è già assegnato'}

    schedule: Schedule = create(Schedule, schedule_data, session=session)
    for user in users:
      create(DeliveryGroup, {'schedule_id': schedule.id, 'user_id': user['id']}, session=session)
    for item in schedule_items:
      handle_schedule_item(item, schedule, session)

    session.commit()
    save_info_to_euronics(schedule_items)
  return {'status': 'ok', 'schedule': schedule.to_dict()}


@schedule_bp.route('<id>', methods=['DELETE'])
@flask_session_authentication([UserRole.ADMIN])
def delete_schedule(user: User, id):
  schedule: Schedule = get_by_id(Schedule, int(id))
  with Session() as session:
    for delivery_group in get_delivery_groups(schedule, session=session):
      delete(delivery_group, session=session)
    delete_schedule_items(get_schedule_items(schedule), session=session)
    delete(schedule, session=session)

    session.commit()
  return {'status': 'ok', 'message': 'Operazione completata'}


@schedule_bp.route('filter', methods=['POST'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN])
def get_schedules(user: User):
  schedules = []
  for tupla in query_schedules(request.json['filters'], 100):
    schedules = format_query_result(tupla, schedules, user)

  if any(filter['model'] == 'Order' and filter['field'] == 'id' for filter in request.json['filters']):
    for schedule in schedules:
      for tupla in get_schedule_item_for_order_id_filter(schedule['id']):
        format_schedule_item(schedule['schedule_items'], tupla[1], tupla[2], tupla[3], tupla[4])

  return {'status': 'ok', 'schedules': schedules}


@schedule_bp.route('<id>', methods=['PUT'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN])
def update_schedule(user: User, id):
  with Session() as session:
    schedule: Schedule = get_by_id(Schedule, int(id), session=session)
    actual_schedule_items = get_schedule_items(schedule, session=session)

    delivery_groups = get_delivery_groups(schedule, session=session)
    deleted_users = []
    if 'deleted_users' in request.json:
      deleted_users = request.json['deleted_users']
      for user_id in deleted_users:
        for delivery_group in delivery_groups:
          if delivery_group.user_id == user_id:
            delete(delivery_group, session=session)
            break
      del request.json['deleted_users']

    schedule_items, schedule_data, users, response = format_schedule_data(request.json, session=session)
    if response:
      return response

    schedule = update(schedule, schedule_data, session=session)
    actual_user_ids = list(set([delivery_group.user_id for delivery_group in delivery_groups]) - set(deleted_users))
    for user in users:
      if user['id'] not in actual_user_ids and query_schedules_count(user['id'], schedule.date) == 0:
        create(DeliveryGroup, {'schedule_id': schedule.id, 'user_id': user['id']}, session=session)

    schedule_items_updating(schedule_items, actual_schedule_items, schedule, session=session)
    session.commit()
    save_info_to_euronics(schedule_items)
  return {'status': 'ok', 'schedule': schedule.to_dict()}


@schedule_bp.route('suggestions', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN])
def get_schedule_suggestions(user: User):
  dpc = datetime.strptime(request.args['dpc'], '%Y-%m-%d')
  orders = []
  for tupla in query_orders(
    user,
    [
      {'model': 'Order', 'field': 'dpc', 'value': dpc},
      {'model': 'Order', 'field': 'status', 'value': OrderStatus.NEW},
    ],
  ):
    orders = format_query_orders_result(tupla, orders, user)
  if len(orders) == 0:
    return {'status': 'ko', 'error': 'Ordini non trovati in questa data'}

  delivery_users = [
    format_user_with_info(delivery_user, user.role) for delivery_user in get_delivery_users_by_date(dpc)
  ]
  return {
    'status': 'ok',
    'delivery_users': delivery_users,
    'transports': [transport.to_dict() for transport in get_transports_by_date(dpc)],
    'groups': assign_orders_to_groups(
      orders,
      delivery_users,
      int(request.args['min_size_group']),
      int(request.args['max_distance_km']),
    ),
  }


@schedule_bp.route('pianification', methods=['POST'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN])
def pianification(user: User):
  orders = []
  for tupla in query_orders(
    user,
    [{'model': 'Order', 'field': 'id', 'value': request.json['orders_id']}],
  ):
    orders = format_query_orders_result(tupla, orders, user)
  if len(orders) == 0:
    return {'status': 'ko', 'error': 'Ordini non identificati'}

  # for order in orders:
  #   if order['status'] != 'New':
  #     return {'status': 'ko', 'error': 'Hai selezionato degli ordini già assegnati'}

  return {'status': 'ok', 'schedule_items': build_schedule_items(orders)}

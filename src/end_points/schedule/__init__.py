from datetime import datetime
from flask import Blueprint, request

from database_api import Session
from ..users.session import flask_session_authentication
from ...database.schema import Schedule, User, DeliveryGroup
from ...database.enum import UserRole, ScheduleType, OrderStatus
from database_api.operations import create, delete, get_by_id, update
from .schedulation import assign_orders_to_groups, build_schedule_items
from ..orders.queries import query_orders, format_query_result as format_query_orders_result
from .utils import handle_schedule_item, delete_schedule_items, clear_order, format_schedule_data
from .queries import (
  query_schedules,
  query_schedules_count,
  format_query_result,
  get_delivery_groups,
  get_schedule_items,
  # get_delivery_users_by_date,
  # get_transports_by_date,
)


schedule_bp = Blueprint('schedule_bp', __name__)


@schedule_bp.route('', methods=['POST'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN])
def create_schedule(user: User):
  with Session() as session:
    schedule_items, schedule_data, users, response = format_schedule_data(request.json, session=session)
    if response:
      return response

    schedule: Schedule = create(Schedule, schedule_data, session=session)
    for user in users:
      if query_schedules_count(user['id'], schedule.date) == 0:
        create(DeliveryGroup, {'schedule_id': schedule.id, 'user_id': user['id']}, session=session)

    for item in schedule_items:
      handle_schedule_item(item, schedule, session)

    session.commit()
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
  return {'status': 'ok', 'schedules': schedules}


@schedule_bp.route('<id>', methods=['PUT'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN])
def update_schedule(user: User, id):
  with Session() as session:
    schedule: Schedule = get_by_id(Schedule, int(id), session=session)
    actual_schedule_items = get_schedule_items(schedule, session=session)
    actual_order_ids = [
      item[2].order_id for item in actual_schedule_items if item[0].operation_type == ScheduleType.ORDER
    ]

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

    for order_id in list(
      set(actual_order_ids)
      - set(
        map(
          lambda schedule_item: schedule_item['order'].id,
          filter(
            lambda schedule_item: ScheduleType.get_enum_option(schedule_item['operation_type']) == ScheduleType.ORDER,
            schedule_items,
          ),
        )
      )
    ):
      clear_order(order_id, session=session)

    for index, item in enumerate(schedule_items):
      if index < len(actual_schedule_items):
        handle_schedule_item(item, schedule, session, actual_order_ids, actual_schedule_items[index])
      else:
        handle_schedule_item(item, schedule, session, actual_order_ids)
    if index < len(actual_schedule_items) - 1:
      delete_schedule_items(actual_schedule_items[index + 1 :], session=session)

    session.commit()
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
      {'model': 'Order', 'field': 'status', 'value': OrderStatus.PENDING},
    ],
  ):
    orders = format_query_orders_result(tupla, orders, user)
  if len(orders) == 0:
    return {'status': 'ko', 'error': 'Not found orders'}

  # delivery_users = get_delivery_users_by_date(dpc)
  # if len(delivery_users) == 0:
  #   return {'status': 'ko', 'error': 'Not found delivery users'}

  # transports = get_transports_by_date(dpc)
  # if len(transports) == 0:
  #   return {'status': 'ko', 'error': 'Not found transports'}

  return {'status': 'ok', 'groups': assign_orders_to_groups(orders)}


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
    return {'status': 'ko', 'error': 'Not found orders'}

  for order in orders:
    if order['status'] != 'Pending':
      return {'status': 'ko', 'error': 'Hai selezionato degli ordini già assegnati'}

  return {'status': 'ok', 'schedule_items': build_schedule_items(orders)}

from datetime import datetime
from flask import Blueprint, request

from database_api import Session
from .sms_sender import schedule_sms_check
from ...database.enum import UserRole, OrderStatus
from ..users.session import flask_session_authentication
from ...database.schema import Schedule, User, Order, DeliveryGroup
from database_api.operations import create, delete, get_by_id, update, get_by_ids
from .queries import (
  query_schedules,
  query_schedules_count,
  get_related_orders,
  format_query_result,
  get_delivery_groups,
)


schedule_bp = Blueprint('schedule_bp', __name__)


@schedule_bp.route('', methods=['POST'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN])
def create_schedule(user: User):
  with Session() as session:
    orders, orders_data_map, schedule_data, users, response = format_schedule_data(request.json, session=session)
    if response:
      return response

    schedule: Schedule = create(Schedule, schedule_data, session=session)
    for user in users:
      if query_schedules_count(user['id'], schedule.date) == 0:
        create(DeliveryGroup, {'schedule_id': schedule.id, 'user_id': user['id']}, session=session)

    for order in orders:
      if order.id in orders_data_map:
        order = update(
          order,
          {
            'schedule_id': schedule.id,
            'status': OrderStatus.IN_PROGRESS,
            'assignament_date': datetime.now(),
            'end_time_slot': orders_data_map[order.id]['end_time_slot'],
            'schedule_index': orders_data_map[order.id]['schedule_index'],
            'start_time_slot': orders_data_map[order.id]['start_time_slot'],
          },
          session=session,
        )
        schedule_sms_check(order)

    session.commit()
  return {'status': 'ok', 'schedule': schedule.to_dict()}


@schedule_bp.route('<id>', methods=['DELETE'])
@flask_session_authentication([UserRole.ADMIN])
def delete_schedule(user: User, id):
  schedule = get_by_id(Schedule, int(id))
  orders = get_related_orders(schedule)
  for delivery_group in get_delivery_groups(schedule):
    delete(delivery_group)
  delete(schedule)
  for order in orders:
    update(order, {'schedule_id': None, 'assignament_date': None, 'status': OrderStatus.PENDING})
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
    if 'deleted_orders' in request.json:
      for order in get_by_ids(Order, request.json['deleted_orders'], session=session):
        update(order, {'schedule_id': None, 'assignament_date': None, 'status': OrderStatus.PENDING}, session=session)
      del request.json['deleted_orders']

    schedule: Schedule = get_by_id(Schedule, int(id), session=session)
    delivery_groups = get_delivery_groups(schedule)
    deleted_users = []
    if 'deleted_users' in request.json:
      deleted_users = request.json['deleted_users']
      for user_id in deleted_users:
        for delivery_group in delivery_groups:
          if delivery_group.user_id == user_id:
            delete(delivery_group, session=session)
            break
      del request.json['deleted_users']

    orders, orders_data_map, schedule_data, users, response = format_schedule_data(request.json, session=session)
    if response:
      return response

    schedule = update(schedule, schedule_data, session=session)
    actual_user_ids = list(set([delivery_group.user_id for delivery_group in delivery_groups]) - set(deleted_users))
    for user in users:
      if user['id'] not in actual_user_ids and query_schedules_count(user['id'], schedule.date) == 0:
        create(DeliveryGroup, {'schedule_id': schedule.id, 'user_id': user['id']}, session=session)

    for order in orders:
      if order.id in orders_data_map:
        data_update = orders_data_map[order.id]
        diff = {
          'schedule_id': schedule.id,
          'start_time_slot': data_update['start_time_slot'],
          'end_time_slot': data_update['end_time_slot'],
          'schedule_index': data_update['schedule_index'],
        }
        if order.status == OrderStatus.PENDING:
          diff['status'] = OrderStatus.IN_PROGRESS
        if not order.assignament_date:
          diff['assignament_date'] = datetime.now()
        was_unscheduled = order.schedule_id is None
        order = update(order, diff, session=session)

        schedule_sms_check(order, was_unscheduled)
    session.commit()
  return {'status': 'ok', 'schedule': schedule.to_dict()}


def format_schedule_data(schedule_data: dict, session=None) -> list[list[Order], dict]:
  orders_data = schedule_data['orders']
  orders: list[Order] = get_by_ids(Order, [o['id'] for o in orders_data], session=session)
  if not orders:
    return None, None, None, None, {'status': 'ko', 'error': 'Errore nella creazione del borderò'}

  del schedule_data['orders']
  if 'order_ids' in schedule_data:
    del schedule_data['order_ids']
  if 'deleted_orders' in schedule_data:
    del schedule_data['deleted_orders']
  if 'transport' in schedule_data:
    del schedule_data['transport']
  users = []
  if 'users' in schedule_data:
    users = schedule_data['users']
    del schedule_data['users']

  orders_data_map = {o['id']: o for o in orders_data}
  return orders, orders_data_map, schedule_data, users, None

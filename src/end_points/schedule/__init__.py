from datetime import datetime
from flask import Blueprint, request

from database_api import Session
from .sms_sender import schedule_sms_check
from ...database.enum import UserRole, OrderStatus
from ..users.session import flask_session_authentication
from database_api.operations import create, delete, get_by_id, update, get_by_ids
from ...database.schema import Schedule, User, Order, DeliveryGroup, CollectionPoint
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
    orders, orders_data_map, schedule_data, users, collection_points, response = format_schedule_data(request.json, session=session)
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

    orders, orders_data_map, schedule_data, users, collection_points, response = format_schedule_data(request.json, session=session)
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


def format_schedule_data(schedule_data: dict, session=None):
  schedule_items = schedule_data['schedule_items']
  orders_data_map = {}
  collection_point_ids = []
  for item in schedule_items:
    if item['operation_type'] == 'Order':
      orders_data_map[int(item['id'])] = {
        'start_time_slot': item['start_time_slot'],
        'end_time_slot': item['end_time_slot'],
        'schedule_index': item['index'],
      }
    elif item['operation_type'] == 'CollectionPoint':
      collection_point_ids.append(item['id'])
  orders: list[Order] = get_by_ids(Order, orders_data_map.keys(), session=session)
  collection_points = list[CollectionPoint] = get_by_ids(CollectionPoint, collection_point_ids, session=session)
  users = schedule_data['users']
  if not orders or not collection_points and not users or len(users) == 0:
    return None, None, None, None, {'status': 'ko', 'error': 'Errore nella creazione del borderò'}

  del schedule_data['users']
  del schedule_data['schedule_items']
  return orders, orders_data_map, schedule_data, users, collection_points, None

from datetime import datetime
from flask import Blueprint, request

from database_api import Session
from .sms_sender import schedule_sms_check
from ..users.session import flask_session_authentication
from ...database.enum import UserRole, OrderStatus, ScheduleType
from database_api.operations import create, delete, get_by_id, update, get_by_ids
from ...database.schema import (
  Schedule,
  User,
  Order,
  DeliveryGroup,
  CollectionPoint,
  ScheduleItem,
  ScheduleItemCollectionPoint,
  ScheduleItemOrder,
)
from .queries import (
  query_schedules,
  query_schedules_count,
  get_related_orders,
  format_query_result,
  get_delivery_groups,
  get_schedule_items,
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

    schedule_items, schedule_data, users, response = format_schedule_data(request.json, session=session)
    if response:
      return response

    schedule = update(schedule, schedule_data, session=session)
    actual_user_ids = list(set([delivery_group.user_id for delivery_group in delivery_groups]) - set(deleted_users))
    for user in users:
      if user['id'] not in actual_user_ids and query_schedules_count(user['id'], schedule.date) == 0:
        create(DeliveryGroup, {'schedule_id': schedule.id, 'user_id': user['id']}, session=session)

    actual_schedule_items = get_schedule_items(schedule, session=session)
    actual_order_ids = [item[0].id for item in actual_schedule_items if item[0].operation_type == ScheduleType.ORDER]
    for index, item in enumerate(schedule_items):
      if index < len(actual_schedule_items):
        handle_schedule_item(item, schedule, session, actual_order_ids, actual_schedule_items[index])
      else:
        handle_schedule_item(item, schedule, session, actual_order_ids)

    session.commit()
  return {'status': 'ok', 'schedule': schedule.to_dict()}


def format_schedule_data(schedule_data: dict, session=None):
  order_ids = []
  schedule_items = []
  collection_point_ids = []
  for item in schedule_data['schedule_items']:
    schedule_item = {
      'index': item['index'],
      'end_time_slot': item['end_time_slot'],
      'operation_type': item['operation_type'],
      'start_time_slot': item['start_time_slot'],
    }
    if item['operation_type'] == 'Order':
      order_ids.append(item['order_id'])
      schedule_item['order_id'] = item['order_id']
    elif item['operation_type'] == 'CollectionPoint':
      collection_point_ids.append(item['collection_point_id'])
      schedule_item['collection_point_id'] = item['collection_point_id']
    schedule_items.append(schedule_item)

  orders: list[Order] = get_by_ids(Order, order_ids, session=session)
  collection_points: list[CollectionPoint] = get_by_ids(CollectionPoint, collection_point_ids, session=session)
  for item in schedule_items:
    if item['operation_type'] == 'Order':
      for order in orders:
        if order.id == item['order_id']:
          item['order'] = order
          break
    elif item['operation_type'] == 'CollectionPoint':
      for collection_point in collection_points:
        if collection_point.id == item['collection_point_id']:
          item['collection_point'] = collection_point
          break

  users = schedule_data['users']
  if not orders or not collection_points and not users or len(users) == 0:
    return None, None, None, {'status': 'ko', 'error': 'Errore nella creazione del borderò'}

  del schedule_data['users']
  del schedule_data['schedule_items']
  return schedule_items, schedule_data, users, None


def handle_schedule_item(
  item: dict,
  schedule: Schedule,
  session,
  actual_order_ids: list[int] = None,
  actual_schedule_item: tuple[ScheduleItem, ScheduleItemCollectionPoint, ScheduleItemOrder] = None,
):
  operation_type = ScheduleType.get_enum_option(item['operation_type'])
  item_diff = {
    'index': item['index'],
    'operation_type': operation_type,
    'end_time_slot': item['end_time_slot'],
    'start_time_slot': item['start_time_slot'],
    'schedule_id': schedule.id,
  }
  if not actual_schedule_item:
    new_item: ScheduleItem = create(ScheduleItem, item_diff, session=session)
  else:
    new_item: ScheduleItem = update(actual_schedule_item[0], item_diff, session=session)

  if operation_type == ScheduleType.ORDER:
    order: Order = item['order']
    item_order_diff = {
      'order_id': order.id,
      'schedule_item_id': new_item.id,
    }
    if actual_schedule_item and actual_schedule_item[2]:
      update(actual_schedule_item[2], item_order_diff, session=session)
    elif actual_schedule_item and not actual_schedule_item[2] and actual_schedule_item[1]:
      delete(actual_schedule_item[1], session=session)
      create(ScheduleItemOrder, item_order_diff, session=session)
    else:
      create(ScheduleItemOrder, item_order_diff, session=session)

    order_diff = {'assignament_date': datetime.now()}
    if order.status == OrderStatus.PENDING:
      order_diff['status'] = OrderStatus.IN_PROGRESS
    was_unscheduled = actual_order_ids and order.id not in actual_order_ids
    order = update(order, order_diff, session=session)
    schedule_sms_check(order, was_unscheduled)

  elif operation_type == ScheduleType.COLLECTIONPOINT:
    item_collection_point_diff = {
      'collection_point_id': item['collection_point'].id,
      'schedule_item_id': new_item.id,
    }
    if actual_schedule_item and actual_schedule_item[1]:
      update(actual_schedule_item[1], item_collection_point_diff, session=session)
    elif actual_schedule_item and not actual_schedule_item[1] and actual_schedule_item[2]:
      delete(actual_schedule_item[2], session=session)
      create(ScheduleItemCollectionPoint, item_collection_point_diff, session=session)
    else:
      create(ScheduleItemCollectionPoint, item_collection_point_diff, session=session)

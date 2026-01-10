from datetime import datetime

from .sms_sender import schedule_sms_check
from ...database.enum import OrderStatus, ScheduleType
from database_api.operations import create, delete, get_by_id, update, get_by_ids
from ...database.schema import (
  CollectionPoint,
  Order,
  Schedule,
  ScheduleItem,
  ScheduleItemCollectionPoint,
  ScheduleItemOrder,
)


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
  if not orders or not collection_points or not users or len(users) == 0:
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
    if was_unscheduled:
      schedule_sms_check(order, new_item)

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


def clear_order(order_id: int, session=None):
  update(
    get_by_id(Order, order_id, session=session),
    {'assignament_date': None, 'status': OrderStatus.PENDING},
    session=session,
  )


def delete_schedule_items(
  schedule_items: list[tuple[ScheduleItem, ScheduleItemCollectionPoint, ScheduleItemOrder]], session=None
):
  for schedule_item in schedule_items:
    if schedule_item[2]:
      delete(schedule_item[2], session=session)
      clear_order(schedule_item[2].order_id, session=session)
    if schedule_item[1]:
      delete(schedule_item[1], session=session)
    delete(schedule_item[0], session=session)

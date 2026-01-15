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


def handle_schedule_item(item: dict, schedule: Schedule, session):
  operation_type = ScheduleType.get_enum_option(item['operation_type'])
  new_item: ScheduleItem = create(
    ScheduleItem,
    {
      'index': item['index'],
      'schedule_id': schedule.id,
      'operation_type': operation_type,
      'end_time_slot': item['end_time_slot'],
      'start_time_slot': item['start_time_slot'],
    },
    session=session,
  )

  if operation_type == ScheduleType.ORDER:
    order: Order = item['order']
    create(
      ScheduleItemOrder,
      {
        'order_id': order.id,
        'schedule_item_id': new_item.id,
      },
      session=session,
    )

  elif operation_type == ScheduleType.COLLECTIONPOINT:
    create(
      ScheduleItemCollectionPoint,
      {
        'schedule_item_id': new_item.id,
        'collection_point_id': item['collection_point'].id,
      },
      session=session,
    )

  return new_item


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


def schedule_items_updating(
  schedule_items: list[dict],
  actual_schedule_items: list[tuple[ScheduleItem, ScheduleItemCollectionPoint, ScheduleItemOrder]],
  schedule: Schedule,
  session,
):
  for schedule_item in schedule_items:
    if 'id' in schedule_item:
      update(
        next(actual_item for actual_item in actual_schedule_items if actual_item[0].id == schedule_item['id']),
        {
          'index': schedule_item['index'],
          'end_time_slot': schedule_item['end_time_slot'],
          'start_time_slot': schedule_item['start_time_slot'],
        },
        session=session,
      )
    else:
      new_item = handle_schedule_item(schedule_item, schedule, session=session)

      if schedule_item['operation_type'] == 'Order':
        order: Order = get_by_id(Order, schedule_item['order_id'], session=session)
        update(order, {'assignament_date': datetime.now(), 'status': OrderStatus.IN_PROGRESS}, session=session)
        schedule_sms_check(order, new_item)

  items_to_delete = []
  for actual_item in actual_schedule_items:
    if actual_item[0].id not in [schedule_item['id'] for schedule_item in schedule_items if 'id' in schedule_item]:
      items_to_delete.append(actual_item)
  delete_schedule_items(items_to_delete, session=session)

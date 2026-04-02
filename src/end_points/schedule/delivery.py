from datetime import date

from ...database.enum import OrderStatus
from database_api.operations import get_by_id, update
from ...database.schema import User, ScheduleItem, Order
from .queries import query_schedules, format_query_result


def get_items_for_delivery(delivery_user: User):
  schedules = []
  for tupla in query_schedules(
    [
      {'model': 'DeliveryGroup', 'field': 'user_id', 'value': delivery_user.id},
      {'model': 'Schedule', 'field': 'date', 'value': [date.today(), date.today()]},
    ],
    get_services=True,
  ):
    schedules = format_query_result(tupla, schedules, delivery_user)
  if len(schedules) != 1:
    return {'status': 'ko', 'message': 'Numero di bordero trovati non valido'}

  return {
    'status': 'ok',
    'schedule_items': sorted(schedules[0]['schedule_items'], key=lambda schedule_item: schedule_item['index']),
  }


def update_schedule_item(delivery_user: User, schedule_item_id: int, completed: bool):
  schedule_item: ScheduleItem = get_by_id(ScheduleItem, schedule_item_id)
  update(schedule_item, {'completed': completed})

  items_response = get_items_for_delivery(delivery_user)
  if items_response['status'] == 'ko':
    return items_response

  schedule_items = items_response['schedule_items']
  for item in schedule_items:
    if item['operation_type'] == 'CollectionPoint':
      continue

    required_cp_ids = [product['collection_point']['id'] for product in item['products'].values()]
    if all(
      collection_point['completed']
      for collection_point in [
        item
        for item in schedule_items
        if item['operation_type'] == 'CollectionPoint' and item['collection_point_id'] in required_cp_ids
      ]
    ):
      order: Order = get_by_id(Order, item['order_id'])
      update(order, {'status': OrderStatus.BOOKING})

  return {'status': 'ok', 'message': 'Operazione completata'}

from datetime import date, timedelta

from database_api.operations import create, get_by_id

from src.database.enum import OrderStatus, ScheduleType, UserRole
from src.database.schema import Order, ScheduleItemCollectionPoint
from src.end_points.schedule.delivery import get_items_for_delivery, update_schedule_item

from tests.unit.factories import (
  auth_header,
  create_collection_point,
  create_delivery_group,
  create_order,
  create_product,
  create_schedule,
  create_schedule_item,
  create_user,
  customer_with_service,
  link_order_to_schedule,
)


def _delivery_with_schedule(schedule_date=None):
  delivery = create_user(UserRole.DELIVERY)
  schedule = create_schedule(schedule_date=schedule_date or date.today())
  create_delivery_group(delivery, schedule)
  return delivery, schedule


def test_get_items_for_delivery_empty_without_todays_schedule(db):
  delivery, _ = _delivery_with_schedule(schedule_date=date.today() + timedelta(days=1))

  result = get_items_for_delivery(delivery)

  assert result == {'status': 'ok', 'schedule_items': []}


def test_get_items_for_delivery_sorted_by_index(db):
  _, _, service_user, _ = customer_with_service()
  delivery, schedule = _delivery_with_schedule()
  first_order = create_order(status=OrderStatus.SCHEDULED)
  create_product(first_order, service_user)
  second_order = create_order(status=OrderStatus.SCHEDULED)
  create_product(second_order, service_user)
  link_order_to_schedule(second_order, schedule, index=2)
  link_order_to_schedule(first_order, schedule, index=1)

  result = get_items_for_delivery(delivery)

  assert result['status'] == 'ok'
  assert [item['index'] for item in result['schedule_items']] == [1, 2]
  assert [item['order_id'] for item in result['schedule_items']] == [first_order.id, second_order.id]


def test_get_items_for_delivery_includes_service_names(db):
  _, service, service_user, _ = customer_with_service()
  delivery, schedule = _delivery_with_schedule()
  order = create_order(status=OrderStatus.SCHEDULED)
  create_product(order, service_user, name='TV')
  link_order_to_schedule(order, schedule)

  result = get_items_for_delivery(delivery)

  item = result['schedule_items'][0]
  assert item['products']['TV']['services'] == [service.name]


def test_update_schedule_item_completes_order_when_collection_points_done(db):
  customer, _, service_user, _ = customer_with_service()
  collection_point = create_collection_point(customer)
  delivery, schedule = _delivery_with_schedule()

  order = create_order(status=OrderStatus.SCHEDULED)
  create_product(order, service_user, collection_point_id=collection_point.id)
  link_order_to_schedule(order, schedule, index=1)

  cp_item = create_schedule_item(schedule, ScheduleType.COLLECTIONPOINT, index=0)
  create(
    ScheduleItemCollectionPoint,
    {'schedule_item_id': cp_item.id, 'collection_point_id': collection_point.id},
  )

  result = update_schedule_item(delivery, cp_item.id, True)

  assert result['status'] == 'ok'
  assert get_by_id(Order, order.id).status == OrderStatus.BOOKING


def test_update_schedule_item_keeps_order_when_collection_point_pending(db):
  customer, _, service_user, _ = customer_with_service()
  collection_point = create_collection_point(customer)
  delivery, schedule = _delivery_with_schedule()

  order = create_order(status=OrderStatus.SCHEDULED)
  create_product(order, service_user, collection_point_id=collection_point.id)
  order_item = link_order_to_schedule(order, schedule, index=1)

  cp_item = create_schedule_item(schedule, ScheduleType.COLLECTIONPOINT, index=0)
  create(
    ScheduleItemCollectionPoint,
    {'schedule_item_id': cp_item.id, 'collection_point_id': collection_point.id},
  )

  # Completa l'item ordine, ma il punto di ritiro non è ancora completato
  result = update_schedule_item(delivery, order_item.id, True)

  assert result['status'] == 'ok'
  assert get_by_id(Order, order.id).status == OrderStatus.SCHEDULED


def test_update_schedule_item_endpoint(client):
  _, _, service_user, _ = customer_with_service()
  delivery, schedule = _delivery_with_schedule()
  order = create_order(status=OrderStatus.SCHEDULED)
  create_product(order, service_user)
  item = link_order_to_schedule(order, schedule)

  response = client.put(
    f'/schedule/item/{item.id}', json={'completed': True}, headers=auth_header(delivery)
  )

  assert response.get_json()['status'] == 'ok'
  from src.database.schema import ScheduleItem

  assert get_by_id(ScheduleItem, item.id).completed is True


def test_get_items_for_delivery_endpoint(client):
  _, _, service_user, _ = customer_with_service()
  delivery, schedule = _delivery_with_schedule()
  order = create_order(status=OrderStatus.SCHEDULED)
  create_product(order, service_user)
  link_order_to_schedule(order, schedule)

  response = client.get('/schedule/delivery', headers=auth_header(delivery))

  body = response.get_json()
  assert body['status'] == 'ok'
  assert len(body['schedule_items']) == 1

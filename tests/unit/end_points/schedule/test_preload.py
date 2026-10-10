from datetime import date, timedelta

from database_api import Session
from database_api.operations import create, get_by_id, update

from src.database.enum import OrderStatus, ScheduleType, UserRole
from src.database.schema import DeliveryCoverageEntry, Order, ScheduleItemCollectionPoint
from src.end_points.schedule.delivery import get_items_for_delivery, update_schedule_item
from src.end_points.schedule.preload import (
  order_is_preloaded,
  preloaded_collection_point_ids,
  preloaded_pickup_ids_for_order,
)

from tests.unit.factories import (
  assign_delivery_user_to_schedule,
  create_collection_point,
  create_order,
  create_product_row,
  create_schedule,
  create_schedule_item,
  create_transport,
  create_user,
  customer_with_service,
  link_order_to_schedule,
)


def _point(customer, preloaded=False):
  return create_collection_point(customer, preloaded=preloaded)


def _stop(schedule, point, index=0):
  item = create_schedule_item(schedule, ScheduleType.COLLECTIONPOINT, index=index)
  create(ScheduleItemCollectionPoint, {'schedule_item_id': item.id, 'collection_point_id': point.id})
  return item


def _delivery(schedule):
  delivery = create_user(UserRole.DELIVERY)
  assign_delivery_user_to_schedule(delivery, schedule)
  return delivery


def _items(delivery):
  return get_items_for_delivery(delivery)['schedule_items']


def test_preloaded_collection_point_ids_keeps_only_preloaded_points(db):
  customer, _, _, _ = customer_with_service()
  preloaded, normal = _point(customer, True), _point(customer)

  with Session() as session:
    assert preloaded_collection_point_ids([preloaded.id, normal.id, None], session) == {preloaded.id}
    assert preloaded_collection_point_ids([], session) == set()


def test_order_is_preloaded_needs_area_and_a_preloaded_point(db):
  customer, _, _, _ = customer_with_service()
  preloaded, normal = _point(customer, True), _point(customer)
  accepting = DeliveryCoverageEntry(accepts_preloads=True)
  refusing = DeliveryCoverageEntry(accepts_preloads=False)

  with Session() as session:
    assert order_is_preloaded(accepting, [normal.id, preloaded.id], session) is True
    assert order_is_preloaded(accepting, [normal.id], session) is False
    assert order_is_preloaded(refusing, [preloaded.id], session) is False
    assert order_is_preloaded(None, [preloaded.id], session) is False


def test_preloaded_pickup_ids_for_order_are_empty_when_order_is_not_preloaded(db):
  customer, _, service_user, _ = customer_with_service()
  point = _point(customer, True)
  order = create_order()
  create_product_row(order, service_user, collection_point_id=point.id)

  with Session() as session:
    assert preloaded_pickup_ids_for_order(order, session) == set()

  order = update(order, {'preloaded': True})
  with Session() as session:
    assert preloaded_pickup_ids_for_order(order, session) == {point.id}


def test_pickup_stop_lists_products_with_next_day_preloads_flagged(db):
  customer, _, service_user, _ = customer_with_service()
  point = _point(customer, True)
  transport = create_transport()
  today = create_schedule(transport, schedule_date=date.today())
  delivery = _delivery(today)
  _stop(today, point, index=0)
  # Ordine di oggi, non precaricato: il ritiro e' normale anche se il punto ammette il precarico.
  same_day = create_order(status=OrderStatus.SCHEDULED, addressee='Mario Rossi')
  create_product_row(same_day, service_user, name='Frigo', collection_point_id=point.id)
  link_order_to_schedule(same_day, today, index=1)
  tomorrow = create_order(
    dpc=date.today() + timedelta(days=1),
    addressee='Anna Bianchi',
    preloaded=True,
    delivery_transport_id=transport.id,
  )
  create_product_row(tomorrow, service_user, name='Lavatrice', collection_point_id=point.id)
  other_vehicle = create_order(
    dpc=date.today() + timedelta(days=1), preloaded=True, delivery_transport_id=create_transport().id
  )
  create_product_row(other_vehicle, service_user, name='Forno', collection_point_id=point.id)

  stop = next(item for item in _items(delivery) if item['operation_type'] == 'CollectionPoint')

  assert stop['has_preload'] is True
  assert [(p['name'], p['preloaded'], p['addressee']) for p in stop['pickup_products']] == [
    ('Frigo', False, 'Mario Rossi'),
    ('Lavatrice', True, 'Anna Bianchi'),
  ]
  assert stop['pickup_products'][1]['order_id'] == tomorrow.id


def test_pickup_stop_without_preloads_has_no_preload_flag(db):
  customer, _, service_user, _ = customer_with_service()
  point = _point(customer)
  today = create_schedule(schedule_date=date.today())
  delivery = _delivery(today)
  order = create_order(status=OrderStatus.SCHEDULED)
  create_product_row(order, service_user, name='Frigo', collection_point_id=point.id)
  link_order_to_schedule(order, today, index=1)
  _stop(today, point)

  stop = next(item for item in _items(delivery) if item['operation_type'] == 'CollectionPoint')

  assert stop['has_preload'] is False
  assert [p['preloaded'] for p in stop['pickup_products']] == [False]


def test_order_stop_marks_preloaded_products_and_does_not_wait_for_their_pickup(db):
  customer, _, service_user, _ = customer_with_service()
  preloaded, normal = _point(customer, True), _point(customer)
  today = create_schedule(schedule_date=date.today())
  delivery = _delivery(today)
  order = create_order(status=OrderStatus.SCHEDULED, preloaded=True)
  create_product_row(order, service_user, name='Frigo', collection_point_id=preloaded.id)
  create_product_row(order, service_user, name='Forno', collection_point_id=normal.id)
  link_order_to_schedule(order, today, index=1)
  normal_stop = _stop(today, normal)

  products = next(item for item in _items(delivery) if item.get('order_id') == order.id)['products']
  assert products['Frigo']['preloaded'] is True
  assert 'preloaded' not in products['Forno']

  # Il ritiro del punto normale basta a sbloccare l'ordine: quello precaricato e' di ieri.
  update_schedule_item(delivery, normal_stop.id, True)

  assert get_by_id(Order, order.id).status == OrderStatus.BOOKING

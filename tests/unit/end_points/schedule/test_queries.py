from datetime import date, timedelta

from src.database.enum import OrderStatus, ScheduleType, UserRole
from src.end_points.schedule.queries import (
  get_delivery_groups,
  get_delivery_groups_by_order_id,
  get_delivery_users_by_date,
  get_schedule_by_order,
  get_schedule_item_by_order,
  get_schedule_items,
  get_transports_by_date,
  query_schedules,
  query_schedules_count,
)

from database_api.operations import create
from src.database.schema import ScheduleItemCollectionPoint

from tests.unit.factories import (
  create_collection_point,
  create_delivery_group,
  create_order,
  create_product,
  create_schedule,
  create_schedule_item,
  create_transport,
  create_user,
  customer_with_service,
  link_order_to_schedule,
)


def _full_schedule(service_user, schedule_date=None):
  order = create_order(status=OrderStatus.SCHEDULED)
  create_product(order, service_user)
  schedule = create_schedule(schedule_date=schedule_date)
  item = link_order_to_schedule(order, schedule)
  delivery = create_user(UserRole.DELIVERY)
  create_delivery_group(delivery, schedule)
  return order, schedule, item, delivery


def test_query_schedules_by_id(db):
  _, _, service_user, _ = customer_with_service()
  order, schedule, item, delivery = _full_schedule(service_user)

  results = query_schedules([{'model': 'Schedule', 'field': 'id', 'value': schedule.id}])

  assert len(results) == 1
  row = results[0]
  assert row[0].id == schedule.id
  assert row[2].id == item.id
  assert row[4].id == order.id
  assert row[6].id == delivery.id


def test_query_schedules_by_date_range(db):
  _, _, service_user, _ = customer_with_service()
  _, schedule, _, _ = _full_schedule(service_user, schedule_date=date(2026, 7, 15))
  _full_schedule(service_user, schedule_date=date(2026, 9, 1))

  results = query_schedules([{'model': 'Schedule', 'field': 'date', 'value': ['2026-07-14', '2026-07-16']}])

  assert {row[0].id for row in results} == {schedule.id}


def test_query_schedules_created_at_exact_day(db):
  _, _, service_user, _ = customer_with_service()
  _, schedule, _, _ = _full_schedule(service_user)

  results = query_schedules([{'model': 'Schedule', 'field': 'created_at', 'value': date.today().strftime('%Y-%m-%d')}])

  assert {row[0].id for row in results} == {schedule.id}


def test_query_schedules_with_services(db):
  _, service, service_user, _ = customer_with_service()
  order, schedule, _, _ = _full_schedule(service_user)

  results = query_schedules([{'model': 'Schedule', 'field': 'id', 'value': schedule.id}], get_services=True)

  assert len(results[0]) == 8
  assert results[0][7].id == service.id


def test_query_schedules_count(db):
  delivery = create_user(UserRole.DELIVERY)
  schedule = create_schedule(schedule_date=date.today())
  create_delivery_group(delivery, schedule)

  assert query_schedules_count(delivery.id, date.today()) == 1
  assert query_schedules_count(delivery.id, date.today() + timedelta(days=1)) == 0


def test_get_schedule_item_and_schedule_by_order(db):
  order = create_order()
  schedule = create_schedule()
  item = link_order_to_schedule(order, schedule)

  assert get_schedule_item_by_order(order).id == item.id
  assert get_schedule_by_order(order.id).id == schedule.id
  assert get_schedule_item_by_order(create_order()) is None
  assert get_schedule_by_order(create_order().id) is None


def test_get_schedule_items_returns_tuples_by_type(db):
  customer = create_user(UserRole.CUSTOMER)
  collection_point = create_collection_point(customer)
  order = create_order()
  schedule = create_schedule()
  order_item = link_order_to_schedule(order, schedule, index=1)
  cp_item = create_schedule_item(schedule, ScheduleType.COLLECTIONPOINT, index=0)
  create(
    ScheduleItemCollectionPoint,
    {'schedule_item_id': cp_item.id, 'collection_point_id': collection_point.id},
  )

  results = get_schedule_items(schedule)

  assert len(results) == 2
  by_item_id = {row[0].id: row for row in results}
  assert by_item_id[order_item.id][2] is not None  # ScheduleItemOrder
  assert by_item_id[order_item.id][1] is None
  assert by_item_id[cp_item.id][1] is not None  # ScheduleItemCollectionPoint
  assert by_item_id[cp_item.id][2] is None


def test_get_delivery_groups_for_schedule(db):
  delivery = create_user(UserRole.DELIVERY)
  schedule = create_schedule()
  group = create_delivery_group(delivery, schedule)

  results = get_delivery_groups(schedule)

  assert [g.id for g in results] == [group.id]


def test_get_delivery_groups_by_order_id(db):
  order = create_order()
  schedule = create_schedule()
  link_order_to_schedule(order, schedule)
  delivery = create_user(UserRole.DELIVERY)
  group = create_delivery_group(delivery, schedule)

  results = get_delivery_groups_by_order_id(order.id)

  assert [g.id for g in results] == [group.id]
  assert get_delivery_groups_by_order_id(create_order().id) == []


def test_get_delivery_users_by_date_excludes_busy_drivers(db):
  busy = create_user(UserRole.DELIVERY)
  free = create_user(UserRole.DELIVERY)
  create_user(UserRole.CUSTOMER)
  schedule = create_schedule(schedule_date=date.today())
  create_delivery_group(busy, schedule)

  results = get_delivery_users_by_date(date.today())

  assert [user.id for user in results] == [free.id]


def test_get_transports_by_date_excludes_used_vehicles(db):
  used = create_transport()
  free = create_transport()
  create_schedule(used, schedule_date=date.today())

  results = get_transports_by_date(date.today())

  assert [transport.id for transport in results] == [free.id]

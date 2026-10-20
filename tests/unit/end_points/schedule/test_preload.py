from datetime import date, time, timedelta

from database_api import Session
from database_api.operations import create, get_by_id, update

from src.database.enum import OrderStatus, ScheduleType, UserRole
from src.database.schema import (
  CollectionPointPreloadArea,
  DeliveryCoverageEntry,
  Order,
  Schedule,
  ScheduleItemCollectionPoint,
)
from src.end_points.schedule.delivery import get_items_for_delivery, update_schedule_item
from src.end_points.schedule.preload import (
  order_is_preloaded,
  preload_ready_ids,
  preloaded_products_by_stop,
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
  transport = create_transport()
  order = create_order(dpc=date.today() + timedelta(days=1), delivery_transport_id=transport.id)
  create_product_row(order, service_user, collection_point_id=point.id)
  _stop(create_schedule(transport, date.today()), point)

  with Session() as session:
    assert preloaded_pickup_ids_for_order(order, session) == set()

  order = update(order, {'preloaded': True})
  with Session() as session:
    assert preloaded_pickup_ids_for_order(order, session) == {point.id}


def test_preloaded_pickup_ids_for_order_keep_only_points_visited_on_the_eve(db):
  customer, _, service_user, _ = customer_with_service()
  visited, other = _point(customer, True), _point(customer, True)
  transport = create_transport()
  order = create_order(dpc=date.today() + timedelta(days=1), delivery_transport_id=transport.id, preloaded=True)
  create_product_row(order, service_user, collection_point_id=visited.id)
  create_product_row(order, service_user, collection_point_id=other.id)
  _stop(create_schedule(transport, date.today()), visited)

  with Session() as session:
    # Il veicolo la vigilia passa solo da uno dei due punti: l'altro si ritira il giorno stesso.
    assert preloaded_pickup_ids_for_order(order, session) == {visited.id}


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
  link_order_to_schedule(tomorrow, create_schedule(transport, schedule_date=date.today() + timedelta(days=1)))
  other_transport = create_transport()
  other_vehicle = create_order(
    dpc=date.today() + timedelta(days=1), preloaded=True, delivery_transport_id=other_transport.id
  )
  create_product_row(other_vehicle, service_user, name='Forno', collection_point_id=point.id)
  link_order_to_schedule(
    other_vehicle, create_schedule(other_transport, schedule_date=date.today() + timedelta(days=1))
  )
  # Preloaded ma tolto dal borderò: non genera nessun ritiro.
  unplanned = create_order(dpc=date.today() + timedelta(days=1), preloaded=True, delivery_transport_id=transport.id)
  create_product_row(unplanned, service_user, name='Tostapane', collection_point_id=point.id)

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
  # Ieri il veicolo e' passato dal punto precaricato.
  _stop(create(Schedule, {'date': date.today() - timedelta(days=1), 'transport_id': today.transport_id}), preloaded)
  order = create_order(status=OrderStatus.SCHEDULED, preloaded=True, delivery_transport_id=today.transport_id)
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


def get_schedule(transport, day):
  with Session() as session:
    return session.query(Schedule).filter(Schedule.transport_id == transport.id, Schedule.date == day).one()


def _coverage(transport, day, accepts_preloads=True):
  return create(
    DeliveryCoverageEntry,
    {
      'day_of_week': day.weekday(),
      'transport_id': transport.id,
      'start_time': time(8, 0),
      'end_time': time(12, 0),
      'accepts_preloads': accepts_preloads,
    },
  )


def test_preload_ready_ids_needs_the_vehicle_already_passing_on_the_eve(db):
  transport, other = create_transport(), create_transport()
  customer = create_user(UserRole.CUSTOMER)
  point, elsewhere = _point(customer, preloaded=True), _point(customer, preloaded=True)
  target = date.today() + timedelta(days=3)
  eve = target - timedelta(days=1)
  # Il veicolo lavora la vigilia ma non passa dal punto: niente precarico.
  _coverage(transport, eve)
  _stop(create_schedule(transport, eve), elsewhere)
  with Session() as session:
    assert preload_ready_ids(target, transport.id, [point.id], session) == set()
  # Un altro veicolo che passa la vigilia non conta: il precarico lo fa chi consegna.
  _stop(create_schedule(other, eve), point)
  with Session() as session:
    assert preload_ready_ids(target, transport.id, [point.id], session) == set()
  _stop(get_schedule(transport, eve), point, index=1)
  with Session() as session:
    assert preload_ready_ids(target, transport.id, [point.id, elsewhere.id], session) == {point.id, elsewhere.id}
    assert preload_ready_ids(target.isoformat(), transport.id, [point.id], session) == {point.id}
    assert preload_ready_ids(target, None, [point.id], session) == set()


def test_preload_ready_ids_skips_points_visited_on_the_delivery_day(db):
  transport = create_transport()
  customer = create_user(UserRole.CUSTOMER)
  point = _point(customer, preloaded=True)
  target = date.today() + timedelta(days=3)
  _stop(create_schedule(transport, target - timedelta(days=1)), point)
  with Session() as session:
    assert preload_ready_ids(target, transport.id, [point.id], session) == {point.id}
  # Il veicolo passa dal punto anche il giorno della consegna: ordine normale.
  _stop(create_schedule(transport, target), point)
  with Session() as session:
    assert preload_ready_ids(target, transport.id, [point.id], session) == set()


def test_preload_ready_ids_ignores_a_past_eve(db):
  transport = create_transport()
  customer = create_user(UserRole.CUSTOMER)
  point = _point(customer, preloaded=True)
  _stop(create_schedule(transport, date.today()), point)
  _stop(create_schedule(transport, date.today() - timedelta(days=1)), point)
  with Session() as session:
    # La vigilia di oggi e' ancora utile (consegna domani), quella di ieri no.
    assert preload_ready_ids(date.today() + timedelta(days=1), transport.id, [point.id], session) == {point.id}
    assert preload_ready_ids(date.today(), transport.id, [point.id], session) == set()


def test_order_is_preloaded_checks_the_eve_passage_when_dpc_is_given(db):
  transport = create_transport()
  customer = create_user(UserRole.CUSTOMER)
  point = _point(customer, preloaded=True)
  target = date.today() + timedelta(days=3)
  entry = _coverage(transport, target)
  _coverage(transport, target - timedelta(days=1))
  with Session() as session:
    assert order_is_preloaded(entry, [point.id], session) is True
    # Il veicolo lavora la vigilia ma non passa dal punto.
    assert order_is_preloaded(entry, [point.id], session, dpc=target) is False
  _stop(create_schedule(transport, target - timedelta(days=1)), point)
  with Session() as session:
    assert order_is_preloaded(entry, [point.id], session, dpc=target) is True


def test_preloaded_products_by_stop_lists_only_planned_orders_in_one_query(db):
  customer, _, service_user, _ = customer_with_service()
  point = _point(customer, preloaded=True)
  transport = create_transport()
  day = date.today() + timedelta(days=2)

  def order(planned):
    row = update(create_order(dpc=day + timedelta(days=1)), {'preloaded': True, 'delivery_transport_id': transport.id})
    create_product_row(row, service_user, collection_point_id=point.id)
    if planned:
      link_order_to_schedule(row, create_schedule(transport, day + timedelta(days=1)))
    return row

  planned = order(True)
  order(False)
  _stop(create_schedule(transport, day), point)

  with Session() as session:
    result = preloaded_products_by_stop({(day, transport.id, point.id)}, session)
    assert [row_order.id for row_order, _ in result[(day, transport.id, point.id)]] == [planned.id]
    assert preloaded_products_by_stop({(day, transport.id, _point(customer).id)}, session) == {}


def _area(point, caps=None, polygon=None):
  return create(CollectionPointPreloadArea, {'collection_point_id': point.id, 'caps': caps or [], 'polygon': polygon})


def test_point_with_areas_is_preloaded_only_inside_them(db):
  customer, _, _, _ = customer_with_service()
  point = _point(customer, True)
  _area(point, caps=['70051'])
  refusing = DeliveryCoverageEntry(accepts_preloads=False)

  with Session() as session:
    # L'area del punto prevale sulla zona di copertura, anche se questa rifiuta.
    assert order_is_preloaded(refusing, [point.id], session, cap='70051') is True
    assert order_is_preloaded(refusing, [point.id], session, cap='70020') is False


def test_point_with_areas_ignores_zone_that_accepts_preloads(db):
  customer, _, _, _ = customer_with_service()
  point = _point(customer, True)
  _area(point, caps=['70051'])
  accepting = DeliveryCoverageEntry(accepts_preloads=True)

  with Session() as session:
    assert order_is_preloaded(accepting, [point.id], session, cap='70020') is False


def test_point_without_areas_follows_the_zone(db):
  customer, _, _, _ = customer_with_service()
  point = _point(customer, True)
  accepting = DeliveryCoverageEntry(accepts_preloads=True)
  refusing = DeliveryCoverageEntry(accepts_preloads=False)

  with Session() as session:
    assert order_is_preloaded(accepting, [point.id], session, cap='70020') is True
    assert order_is_preloaded(refusing, [point.id], session, cap='70020') is False


def test_polygon_area_matches_by_coordinates(db):
  customer, _, _, _ = customer_with_service()
  point = _point(customer, True)
  _area(point, polygon=[[41.0, 16.0], [41.0, 17.0], [42.0, 17.0], [42.0, 16.0]])
  refusing = DeliveryCoverageEntry(accepts_preloads=False)

  with Session() as session:
    assert order_is_preloaded(refusing, [point.id], session, cap='70020', lat=41.5, lon=16.5) is True
    assert order_is_preloaded(refusing, [point.id], session, cap='70020', lat=43.0, lon=16.5) is False
    assert order_is_preloaded(refusing, [point.id], session, cap='70020') is False


def test_areas_are_per_point(db):
  customer, _, _, _ = customer_with_service()
  with_area, plain = _point(customer, True), _point(customer, True)
  _area(with_area, caps=['70051'])
  accepting = DeliveryCoverageEntry(accepts_preloads=True)

  with Session() as session:
    ids = preloaded_collection_point_ids(
      [with_area.id, plain.id], session, address=('70020', None, None), zone_accepts=accepting.accepts_preloads
    )
    assert ids == {plain.id}

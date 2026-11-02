"""Casi trovati provando la pianificazione automatica sulla demo (21/10/2026).

Ogni test riproduce un ordine o un borderò visto sulla demo: Idea Monopoli
(punto con precarico senza aree), Idea Bari (punto con precarico e area solo
70043) e Idea Triggiano (punto senza precarico), un solo veicolo.
"""

from datetime import date, datetime, time, timedelta
from unittest.mock import patch

from database_api import Session
from database_api.operations import create, get_by_id

from src.database.enum import OrderStatus, ScheduleType
from src.database.schema import (
  CollectionPointPreloadArea,
  DeliveryCoverageEntry,
  Order,
  Schedule,
  ScheduleItemCollectionPoint,
)
from src.end_points.delivery_coverage import (
  _passes_same_pickup_points,
  _slot_still_open,
  schedules_pass_pickup_points,
)
from src.end_points.schedule.preload import preload_ready_ids, vehicle_passes_pickup_point
from src.end_points.schedule.queries import get_schedule_items
from src.end_points.schedule.utils import delete_schedule_items
from src.schedulation.auto_planning import unplan_order

from tests.unit.factories import (
  create_collection_point,
  create_order,
  create_product_row,
  create_schedule,
  create_schedule_item,
  create_transport,
  customer_with_service,
  link_order_to_schedule,
)

DAY = date.today() + timedelta(days=2)
EVE = DAY - timedelta(days=1)


def _stop(schedule, point, index=0):
  item = create_schedule_item(schedule, ScheduleType.COLLECTIONPOINT, index=index)
  create(ScheduleItemCollectionPoint, {'schedule_item_id': item.id, 'collection_point_id': point.id})
  return item


def _products(*points):
  return {f'Prodotto {i}': {'collection_point': {'id': point.id}} for i, point in enumerate(points)}


def _entry(transport):
  return DeliveryCoverageEntry(accepts_preloads=True, transport_id=transport.id, day_of_week=DAY.weekday())


def _stops(schedule_id):
  with Session() as session:
    schedule = session.get(Schedule, schedule_id)
    if schedule is None:
      return None
    rows = sorted(get_schedule_items(schedule, session=session), key=lambda row: row[0].index)
    return [scp.collection_point_id if scp else f'O{sio.order_id}' for _item, scp, sio in rows]


def test_order_in_edit_still_sees_the_pickup_stop_of_its_borderò(db):
  """22198/22199: in modifica il calendario era vuoto perche' la tappa di ritiro non contava."""
  customer, _, service_user, _ = customer_with_service()
  point = create_collection_point(customer, preloaded=True)
  transport = create_transport()
  schedule = create_schedule(transport, DAY)
  _stop(schedule, point)
  order = create_order(status=OrderStatus.SCHEDULED, dpc=DAY, delivery_transport_id=transport.id)
  create_product_row(order, service_user, collection_point_id=point.id)
  link_order_to_schedule(order, schedule, index=1)

  with Session() as session:
    assert schedules_pass_pickup_points(
      {point.id: [DAY]}, session, transport_id=transport.id, exclude_order_id=order.id
    )
    assert _passes_same_pickup_points(_entry(transport), DAY, _products(point), session, exclude_order_id=order.id)


def test_preloaded_order_is_not_a_passage_on_its_delivery_day(db):
  """22202/22203: dopo un ordine precaricato il secondo non lo era piu' e il veicolo tornava al punto."""
  customer, _, service_user, _ = customer_with_service()
  point = create_collection_point(customer, preloaded=True)
  transport = create_transport()
  _stop(create_schedule(transport, EVE), point)
  preloaded = create_order(
    status=OrderStatus.SCHEDULED, dpc=DAY, delivery_transport_id=transport.id, preloaded=True, cap='70124'
  )
  create_product_row(preloaded, service_user, collection_point_id=point.id)
  link_order_to_schedule(preloaded, create_schedule(transport, DAY))

  with Session() as session:
    assert not vehicle_passes_pickup_point(DAY, transport.id, point.id, session)
    assert preload_ready_ids(DAY, transport.id, {point.id}, session) == {point.id}


def test_point_outside_its_preload_area_follows_the_normal_rules(db):
  """22200 e MW Bari 2 (22/10): fuori dall'area del punto l'ordine non e' un precarico.

  Idea Bari ha l'area solo sul 70043: verso il 70124 non si precarica e la
  fascia segue le regole normali, senza bisogno di passaggi. Dentro l'area
  serve il passaggio del veicolo (qui la vigilia).
  """
  customer, _, _, _ = customer_with_service()
  point = create_collection_point(customer, preloaded=True)
  create(CollectionPointPreloadArea, {'collection_point_id': point.id, 'caps': ['70043'], 'polygon': None})
  transport = create_transport()

  with Session() as session:
    entry = _entry(transport)
    assert _passes_same_pickup_points(entry, DAY, _products(point), session, address=('70124', None, None))
    assert not _passes_same_pickup_points(entry, DAY, _products(point), session, address=('70043', None, None))

  _stop(create_schedule(transport, EVE), point)
  with Session() as session:
    assert _passes_same_pickup_points(_entry(transport), DAY, _products(point), session, address=('70043', None, None))


def test_every_preloaded_pickup_point_of_the_order_needs_its_own_passage(db):
  """22202: col solo passaggio di Idea Monopoli, un secondo punto precaricato apriva un ritiro nuovo.

  Il punto senza precarico (Idea Triggiano) segue le regole normali: non chiede passaggi.
  """
  customer, _, _, _ = customer_with_service()
  passing = create_collection_point(customer, preloaded=True)
  not_passing = create_collection_point(customer, preloaded=True)
  normal = create_collection_point(customer)
  transport = create_transport()
  _stop(create_schedule(transport, EVE), passing)

  with Session() as session:
    entry = _entry(transport)
    assert not _passes_same_pickup_points(entry, DAY, _products(passing, not_passing), session)
    assert _passes_same_pickup_points(entry, DAY, _products(passing), session)
    assert _passes_same_pickup_points(entry, DAY, _products(passing, normal), session)


def test_borderò_left_empty_by_the_planning_is_deleted(db):
  """1524: lo spostamento dell'unico ordine lasciava un borderò vuoto che bloccava il veicolo."""
  transport = create_transport()
  schedule = create_schedule(transport, DAY)
  order = create_order(status=OrderStatus.SCHEDULED, dpc=DAY, delivery_transport_id=transport.id)
  link_order_to_schedule(order, schedule)

  with Session() as session:
    unplan_order(session.get(Order, order.id), session)
    session.commit()

  assert get_by_id(Schedule, schedule.id) is None
  assert get_by_id(Order, order.id).status == OrderStatus.BOOKED


def test_order_leaving_its_borderò_releases_the_eve_preload_pickup(db):
  """1523 cancellato: la tappa della vigilia restava vuota e l'ordine precaricato."""
  customer, _, service_user, _ = customer_with_service()
  point = create_collection_point(customer, preloaded=True)
  other = create_collection_point(customer)
  transport = create_transport()
  eve = create_schedule(transport, EVE)
  _stop(eve, point)
  _stop(eve, other, index=1)
  day = create_schedule(transport, DAY)
  order = create_order(
    status=OrderStatus.SCHEDULED, dpc=DAY, delivery_transport_id=transport.id, preloaded=True, cap='70124'
  )
  create_product_row(order, service_user, collection_point_id=point.id)
  link_order_to_schedule(order, day)

  with Session() as session:
    rows = get_schedule_items(session.get(Schedule, day.id), session=session)
    delete_schedule_items(rows, session=session)
    session.commit()

  assert _stops(eve.id) == [other.id]
  assert get_by_id(Order, order.id).preloaded is False


def test_removed_eve_pickup_turns_next_day_preload_into_a_normal_pickup(db):
  """Senza la tappa della vigilia il precarico non c'e' piu': il ritiro va nel borderò della consegna."""
  customer, _, service_user, _ = customer_with_service()
  point = create_collection_point(customer, preloaded=True)
  other = create_collection_point(customer)
  transport = create_transport()
  eve = create_schedule(transport, EVE)
  eve_stop = _stop(eve, point)
  _stop(eve, other, index=1)
  day = create_schedule(transport, DAY)
  order = create_order(
    status=OrderStatus.SCHEDULED, dpc=DAY, delivery_transport_id=transport.id, preloaded=True, cap='70124'
  )
  create_product_row(order, service_user, collection_point_id=point.id)
  link_order_to_schedule(order, day, start_time_slot=time(9, 0), end_time_slot=time(12, 0))

  with Session() as session:
    rows = [
      row for row in get_schedule_items(session.get(Schedule, eve.id), session=session) if row[0].id == eve_stop.id
    ]
    delete_schedule_items(rows, session=session)
    session.commit()

  assert get_by_id(Order, order.id).preloaded is False
  assert sorted(map(str, _stops(day.id))) == sorted([str(point.id), f'O{order.id}'])
  assert _stops(eve.id) == [other.id]


def test_today_slots_already_over_are_not_offered(db):
  entry = DeliveryCoverageEntry(start_time=time(9, 0), end_time=time(12, 0))
  today = date(2026, 10, 21)

  def at(hour):
    return patch(
      'src.end_points.delivery_coverage.datetime',
      **{'now.return_value': datetime(2026, 10, 21, hour, 0)},
    )

  with at(11):
    assert _slot_still_open(entry, today)
  with at(12):
    assert not _slot_still_open(entry, today)
    assert _slot_still_open(entry, today + timedelta(days=1))

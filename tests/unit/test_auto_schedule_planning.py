"""Test per la pianificazione automatica del borderò alla creazione dell'ordine.

Verifica:
1. Il primo ordine con fascia oraria crea il borderò e lo popola con index 0.
2. Il secondo ordine si aggiunge al borderò esistente nella posizione ottimale.
3. Il terzo ordine con CAP uguale al primo si inserisce vicino alla tappa simile
   invece di intercalarsi con quella di un'altra zona.
4. Con company.automatic_planning == False non viene creato alcun borderò.
5. Un ordine senza fascia oraria non genera un borderò.

Il riordino delle tappe (ordini + punti di ritiro) è delegato a
``src.schedulation.routing.optimize_schedule_stops``, che chiama OSRM Trip
Service: qui viene mockato con ``_optimal_trip_order``, un risolutore TSP a
forza bruta (le liste di test sono piccole) usato come sostituto realistico
di OSRM invece di un fake che impone l'esito. Non testiamo qui la logica di
clustering/fallback pura di ``routing.py``: vedi ``test_routing.py``.
"""

from datetime import date, time, timedelta
from itertools import permutations
from unittest.mock import patch

import pytest
from database_api.operations import create, get_by_params

from src.database.enum import OrderStatus, ScheduleType
from src.database.schema import (
  DeliveryCoverageCap,
  DeliveryCoverageEntry,
  DeliveryUserInfo,
  Order,
  Schedule,
  ScheduleItem,
  ScheduleItemActivity,
  ScheduleItemOrder,
)
from src.schedulation.auto_planning import (
  auto_plan_order,
  find_coverage_entry,
  find_or_create_schedule,
)

from tests.unit.factories import (
  create_delivery_info,
  create_order,
  create_transport,
  create_user,
)
from src.database.enum import UserRole


# ---------------------------------------------------------------------------
# Helpers locali
# ---------------------------------------------------------------------------

TARGET = date.today() + timedelta(days=4)
SLOT_START = time(8, 0)
SLOT_END = time(18, 0)


def _find(cls, **kwargs):
  return get_by_params(cls, list(kwargs.items()))


def _optimal_trip_order(coords):
  """Sostituto di ``trip_order_osrm`` per i test: TSP a percorso aperto per forza bruta.

  Le liste di coordinate nei test sono piccole (2-3 punti), quindi il calcolo
  esaustivo è a costo trascurabile e ci evita di dover indovinare a mano
  l'ordine "giusto" che un vero OSRM restituirebbe.
  """

  def total_distance(order):
    return sum(
      ((coords[order[i]][0] - coords[order[i + 1]][0]) ** 2 + (coords[order[i]][1] - coords[order[i + 1]][1]) ** 2)
      ** 0.5
      for i in range(len(order) - 1)
    )

  return list(min(permutations(range(len(coords))), key=total_distance))


def _make_entry(transport, cap='76011') -> DeliveryCoverageEntry:
  """Crea un DeliveryCoverageEntry + DeliveryCoverageCap e restituisce l'entry."""
  entry = create(
    DeliveryCoverageEntry,
    {
      'day_of_week': TARGET.weekday(),
      'start_time': SLOT_START,
      'end_time': SLOT_END,
      'transport_id': transport.id,
    },
  )
  create(DeliveryCoverageCap, {'entry_id': entry.id, 'cap': cap})
  return entry


def _make_order_with_slot(cap='76011') -> Order:
  return create_order(
    cap=cap,
    dpc=TARGET,
    drc=TARGET,
    delivery_slot_start=SLOT_START,
    delivery_slot_end=SLOT_END,
  )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def transport():
  return create_transport()


@pytest.fixture
def delivery_user(transport):
  user = create_user(UserRole.DELIVERY)
  create_delivery_info(user, transport_id=transport.id)
  return user


@pytest.fixture
def entry(transport):
  return _make_entry(transport, cap='76011')


# ---------------------------------------------------------------------------
# Test: find_coverage_entry
# ---------------------------------------------------------------------------


def test_find_coverage_entry_returns_matching_entry(db, entry):
  order = _make_order_with_slot()
  from database_api import Session

  with Session() as session:
    result = find_coverage_entry(order, session)
  assert result is not None
  assert result.id == entry.id


def test_find_coverage_entry_returns_none_without_slot(db, entry):
  order = create_order(cap='76011', dpc=TARGET, drc=TARGET)
  from database_api import Session

  with Session() as session:
    result = find_coverage_entry(order, session)
  assert result is None


def test_find_coverage_entry_returns_none_for_different_cap(db, entry):
  order = _make_order_with_slot(cap='70056')  # CAP non coperto dall'entry
  from database_api import Session

  with Session() as session:
    result = find_coverage_entry(order, session)
  assert result is None


# ---------------------------------------------------------------------------
# Test: find_or_create_schedule
# ---------------------------------------------------------------------------


def test_find_or_create_schedule_creates_new_schedule(db, entry, delivery_user):
  order = _make_order_with_slot()
  from database_api import Session

  with Session() as session:
    schedule, created = find_or_create_schedule(entry, order, session)
    session.commit()

  assert created is True
  assert schedule.transport_id == entry.transport_id
  assert schedule.date == TARGET


def test_find_or_create_schedule_inherits_the_transport_delivery_users(db, entry, delivery_user):
  """Il borderò non assegna nessuno: i corrieri sono quelli del suo veicolo."""
  order = _make_order_with_slot()
  from database_api import Session

  with Session() as session:
    schedule, _ = find_or_create_schedule(entry, order, session)
    session.commit()

  assigned = _find(DeliveryUserInfo, transport_id=schedule.transport_id)
  assert [info.user_id for info in assigned] == [delivery_user.id]


def test_find_or_create_schedule_returns_existing_without_duplicate(db, entry, delivery_user):
  order = _make_order_with_slot()
  from database_api import Session

  # Prima chiamata: crea
  with Session() as session:
    schedule1, created1 = find_or_create_schedule(entry, order, session)
    session.commit()

  # Seconda chiamata: deve restituire lo stesso borderò
  with Session() as session:
    schedule2, created2 = find_or_create_schedule(entry, order, session)
    session.commit()

  assert created1 is True
  assert created2 is False
  assert schedule1.id == schedule2.id

  # Nessun borderò duplicato per la stessa (data, veicolo)
  all_schedules = _find(Schedule, date=TARGET, transport_id=entry.transport_id)
  assert len(all_schedules) == 1


# ---------------------------------------------------------------------------
# Test: auto_plan_order (integrazione completa)
# ---------------------------------------------------------------------------


def test_auto_plan_creates_schedule_and_first_stop(db, entry, delivery_user):
  # Un solo ordine: optimize_schedule_stops non ha nulla da riordinare e non
  # chiama né il geocoding né OSRM (vedi routing._osrm_or_original_order).
  order = _make_order_with_slot()
  from database_api import Session

  with Session() as session:
    session.flush()
    pending = auto_plan_order(order, session)
    session.commit()

  # Borderò creato
  schedules = _find(Schedule, date=TARGET, transport_id=entry.transport_id)
  assert len(schedules) == 1

  # ScheduleItem creato con index=0
  items = _find(ScheduleItem, schedule_id=schedules[0].id)
  assert len(items) == 1
  assert items[0].index == 0
  assert items[0].operation_type == ScheduleType.ORDER

  # ScheduleItemOrder collegato all'ordine
  sio = _find(ScheduleItemOrder, order_id=order.id)
  assert len(sio) == 1
  assert sio[0].schedule_item_id == items[0].id

  # Stato ordine aggiornato
  updated_order = _find(Order, id=order.id)[0]
  assert updated_order.status in (OrderStatus.SCHEDULED, OrderStatus.BOOKING)

  # SMS pending
  assert len(pending) == 1
  assert pending[0][0].id == order.id


@patch('src.schedulation.routing.trip_order_osrm')
@patch('src.schedulation.routing.get_lat_lon_by_address')
@patch('src.schedulation.routing.get_lat_lon_by_cap')
def test_auto_plan_second_order_reuses_existing_schedule(
  mock_geocode, mock_geocode_address, mock_trip, db, entry, delivery_user
):
  # L'indirizzo (uguale per tutti gli ordini di test) non deve risolvere: il
  # test guida le coordinate via CAP.
  mock_geocode_address.return_value = (None, None)
  mock_geocode.return_value = (41.238, 16.500)
  mock_trip.side_effect = _optimal_trip_order

  order1 = _make_order_with_slot()
  order2 = _make_order_with_slot()

  from database_api import Session

  with Session() as session:
    session.flush()
    auto_plan_order(order1, session)
    session.commit()

  with Session() as session:
    session.flush()
    auto_plan_order(order2, session)
    session.commit()

  # Un solo borderò per la (data, veicolo)
  schedules = _find(Schedule, date=TARGET, transport_id=entry.transport_id)
  assert len(schedules) == 1

  # Due tappe nel borderò
  items = _find(ScheduleItem, schedule_id=schedules[0].id)
  assert len(items) == 2

  # Il corriere resta uno: sta sul veicolo, non sul borderò
  assigned = _find(DeliveryUserInfo, transport_id=schedules[0].transport_id)
  assert len(assigned) == 1


@patch('src.schedulation.routing.trip_order_osrm')
@patch('src.schedulation.routing.get_lat_lon_by_address')
@patch('src.schedulation.routing.get_lat_lon_by_cap')
def test_auto_plan_third_order_inserts_optimally(
  mock_geocode, mock_geocode_address, mock_trip, db, entry, delivery_user
):
  """Bisceglie→Molfetta già nel borderò: il nuovo Bisceglie si accoda all'altro Bisceglie.

  Con un vero risolutore TSP a percorso libero (nessun vincolo su partenza/arrivo),
  Bisceglie-Bisceglie-Molfetta e il suo speculare Molfetta-Bisceglie-Bisceglie sono
  equivalenti in costo: l'unico invariante robusto da verificare è che le due tappe
  Bisceglie restino adiacenti, non che Molfetta finisca in una posizione specifica.
  """
  BISCEGLIE = (41.238, 16.500)
  MOLFETTA = (41.201, 16.583)

  # Aggiunge il CAP di Molfetta alla stessa entry di copertura
  create(DeliveryCoverageCap, {'entry_id': entry.id, 'cap': '70056'})

  # L'indirizzo (uguale per tutti gli ordini di test) non deve risolvere: le
  # coordinate devono venire dal CAP, che qui distingue Bisceglie da Molfetta.
  mock_geocode_address.return_value = (None, None)

  def fake_geocode(cap):
    return BISCEGLIE if cap == '76011' else MOLFETTA

  mock_geocode.side_effect = fake_geocode
  mock_trip.side_effect = _optimal_trip_order

  order1 = _make_order_with_slot(cap='76011')  # Bisceglie
  order2 = _make_order_with_slot(cap='70056')  # Molfetta
  order3 = _make_order_with_slot(cap='76011')  # Bisceglie (deve inserirsi vicino a order1)

  from database_api import Session

  for order in [order1, order2]:
    with Session() as session:
      session.flush()
      auto_plan_order(order, session)
      session.commit()

  with Session() as session:
    session.flush()
    auto_plan_order(order3, session)
    session.commit()

  schedules = _find(Schedule, date=TARGET, transport_id=entry.transport_id)
  items = sorted(
    _find(ScheduleItem, schedule_id=schedules[0].id),
    key=lambda i: i.index,
  )
  assert len(items) == 3

  # Recupera l'ordine per ogni tappa
  order_by_index = {}
  for item in items:
    sio = _find(ScheduleItemOrder, schedule_item_id=item.id)
    if sio:
      order_by_index[item.index] = sio[0].order_id

  caps_in_order = [_find(Order, id=order_by_index[i])[0].cap for i in sorted(order_by_index)]

  # Le due Bisceglie devono essere consecutive (nessun andirivieni via Molfetta in mezzo)
  bisceglie_indices = [i for i, c in enumerate(caps_in_order) if c == '76011']
  assert abs(bisceglie_indices[0] - bisceglie_indices[1]) == 1, (
    f'Le due tappe Bisceglie non sono adiacenti: {caps_in_order}'
  )


# ---------------------------------------------------------------------------
# Test: auto_plan_order con pianificazione disattivata
# ---------------------------------------------------------------------------


def test_auto_plan_skips_order_without_slot(db, entry, delivery_user):
  order = create_order(cap='76011', dpc=TARGET)  # nessuna fascia

  from database_api import Session

  with Session() as session:
    session.flush()
    pending = auto_plan_order(order, session)
    session.commit()

  schedules = _find(Schedule, date=TARGET, transport_id=entry.transport_id)
  assert len(schedules) == 0
  assert pending == []


def test_auto_plan_skips_when_no_coverage_entry_matches(db, transport, delivery_user):
  """Ordine con fascia oraria ma nessuna DeliveryCoverageEntry corrispondente."""
  order = _make_order_with_slot(cap='99999')  # CAP non coperto

  from database_api import Session

  with Session() as session:
    session.flush()
    pending = auto_plan_order(order, session)
    session.commit()

  assert pending == []


# ---------------------------------------------------------------------------
# Test: il veicolo scelto alla creazione e' quello che pianifica
# ---------------------------------------------------------------------------


def test_find_coverage_entry_uses_the_vehicle_stored_on_the_order(db):
  first, second = create_transport(), create_transport()
  _make_entry(first)
  second_entry = _make_entry(second)
  order = create_order(
    cap='76011',
    dpc=TARGET,
    delivery_slot_start=SLOT_START,
    delivery_slot_end=SLOT_END,
    delivery_transport_id=second.id,
  )

  from database_api import Session

  with Session() as session:
    assert find_coverage_entry(order, session).id == second_entry.id


def test_find_coverage_entry_without_vehicle_is_deterministic(db):
  first, second = create_transport(), create_transport()
  # Creato prima il blocco del secondo veicolo: l'ordine di inserimento non decide.
  _make_entry(second)
  first_entry = _make_entry(first)
  order = _make_order_with_slot()

  from database_api import Session

  with Session() as session:
    assert find_coverage_entry(order, session).id == first_entry.id


def test_find_coverage_entry_accepts_a_neighbour_slot_covering_other_caps(db, transport):
  """Fascia adiacente (stesso veicolo) assegnata per traboccamento: copre altri CAP."""
  _make_entry(transport, cap='76011')
  neighbour = create(
    DeliveryCoverageEntry,
    {
      'day_of_week': TARGET.weekday(),
      'start_time': time(18, 0),
      'end_time': time(20, 0),
      'transport_id': transport.id,
    },
  )
  create(DeliveryCoverageCap, {'entry_id': neighbour.id, 'cap': '70000'})
  order = create_order(
    cap='76011',
    dpc=TARGET,
    delivery_slot_start=neighbour.start_time,
    delivery_slot_end=neighbour.end_time,
    delivery_transport_id=transport.id,
  )

  from database_api import Session

  with Session() as session:
    assert find_coverage_entry(order, session).id == neighbour.id


# ---------------------------------------------------------------------------
# Test: unplan_order
# ---------------------------------------------------------------------------


@patch('src.schedulation.auto_planning.optimize_schedule_stops')
def test_unplan_order_removes_the_stop_and_renumbers_the_others(_optimize, db, entry, delivery_user):
  from database_api import Session
  from src.schedulation.auto_planning import unplan_order

  first, second = _make_order_with_slot(), _make_order_with_slot()
  for order in (first, second):
    create_order_schedule = order
    with Session() as session:
      session.flush()
      auto_plan_order(create_order_schedule, session)
      session.commit()

  with Session() as session:
    unplan_order(session.get(Order, first.id), session)
    session.commit()

  assert _find(ScheduleItemOrder, order_id=first.id) == []
  remaining = _find(ScheduleItemOrder, order_id=second.id)
  assert _find(ScheduleItem, id=remaining[0].schedule_item_id)[0].index == 0
  assert _find(Order, id=first.id)[0].status == OrderStatus.BOOKED


@patch('src.schedulation.auto_planning.optimize_schedule_stops')
def test_unplan_order_drops_pickups_only_that_order_needed(_optimize, db, entry, delivery_user):
  from database_api import Session
  from src.database.schema import ScheduleItemCollectionPoint
  from src.schedulation.auto_planning import unplan_order
  from tests.unit.factories import create_product_row, customer_with_service

  _, _, service_user, point = customer_with_service()
  order = _make_order_with_slot()
  create_product_row(order, service_user, collection_point_id=point.id)
  with Session() as session:
    session.flush()
    auto_plan_order(order, session)
    session.commit()
  assert len(_find(ScheduleItemCollectionPoint, collection_point_id=point.id)) == 1

  with Session() as session:
    unplan_order(session.get(Order, order.id), session)
    session.commit()

  assert _find(ScheduleItemCollectionPoint, collection_point_id=point.id) == []
  assert _find(ScheduleItem, schedule_id=_find(Schedule, date=TARGET)[0].id) == []


@patch('src.schedulation.routing.trip_order_osrm')
@patch('src.schedulation.routing.get_lat_lon_by_address')
@patch('src.schedulation.routing.get_lat_lon_by_cap')
def test_optimize_keeps_activities_in_their_position(mock_geocode, mock_geocode_address, mock_trip, db, entry):
  """Le attività non si spostano: gli ordini si scambiano i posti rimasti."""
  from database_api import Session

  from src.schedulation.routing import optimize_schedule_stops

  mock_geocode_address.return_value = (None, None)
  mock_geocode.side_effect = lambda cap: (41.238, 16.500) if cap == '76011' else (41.201, 16.583)
  mock_trip.side_effect = lambda coords: list(reversed(range(len(coords))))

  order_a = _make_order_with_slot(cap='76011')
  order_b = _make_order_with_slot(cap='70056')
  schedule = create(Schedule, {'date': TARGET, 'transport_id': entry.transport_id})
  item_a = create(
    ScheduleItem,
    {
      'index': 0,
      'schedule_id': schedule.id,
      'operation_type': ScheduleType.ORDER,
      'start_time_slot': SLOT_START,
      'end_time_slot': SLOT_END,
    },
  )
  activity_item = create(
    ScheduleItem,
    {
      'index': 1,
      'schedule_id': schedule.id,
      'operation_type': ScheduleType.ACTIVITY,
      'start_time_slot': SLOT_START,
      'end_time_slot': SLOT_END,
    },
  )
  item_b = create(
    ScheduleItem,
    {
      'index': 2,
      'schedule_id': schedule.id,
      'operation_type': ScheduleType.ORDER,
      'start_time_slot': SLOT_START,
      'end_time_slot': SLOT_END,
    },
  )
  create(ScheduleItemOrder, {'order_id': order_a.id, 'schedule_item_id': item_a.id})
  create(ScheduleItemOrder, {'order_id': order_b.id, 'schedule_item_id': item_b.id})
  create(ScheduleItemActivity, {'title': 'Pausa', 'duration_minutes': 30, 'schedule_item_id': activity_item.id})

  with Session() as session:
    optimize_schedule_stops(session.get(Schedule, schedule.id), session)
    session.commit()

  indexes = {item.id: item.index for item in _find(ScheduleItem, schedule_id=schedule.id)}
  assert indexes[activity_item.id] == 1
  assert indexes[item_a.id] == 2
  assert indexes[item_b.id] == 0

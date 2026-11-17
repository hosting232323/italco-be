from datetime import time
from types import SimpleNamespace

from src.schedulation.routing import (
  StopContext,
  _group_by_slot,
  _sequence_slot,
)
from src.schedulation.sequencing import duration_matrix

MORNING = (time(9, 40), time(11, 30))
NOON = (time(11, 30), time(12, 30))


def _item(id, slot=MORNING):
  return SimpleNamespace(id=id, index=0, start_time_slot=slot[0], end_time_slot=slot[1])


def _order_stop(id, coord=(41.0, 16.0), slot=MORNING):
  return StopContext(item=_item(id, slot), kind='order', coord=coord, entity_id=id)


def _cp_stop(id, coord=(41.0, 16.0), slot=MORNING):
  return StopContext(item=_item(id, slot), kind='collection_point', coord=coord, entity_id=id)


# ---------------------------------------------------------------------------
# _group_by_slot
# ---------------------------------------------------------------------------


def test_group_by_slot_orders_slots_chronologically():
  noon, morning = _order_stop(1, slot=NOON), _order_stop(2, slot=MORNING)

  groups = _group_by_slot([noon, morning], [], dependencies={})

  assert groups == [([morning], []), ([noon], [])]


def test_group_by_slot_moves_a_shared_pickup_to_the_earliest_slot_needing_it():
  # Il ritiro nasce nella fascia del primo ordine pianificato (mezzogiorno) ma
  # serve anche un ordine del mattino: va fatto prima di quello.
  noon, morning = _order_stop(1, slot=NOON), _order_stop(2, slot=MORNING)
  cp = _cp_stop(10, slot=NOON)

  groups = _group_by_slot([noon, morning], [cp], {noon.item.id: {10}, morning.item.id: {10}})

  assert groups == [([morning], [cp]), ([noon], [])]


def test_group_by_slot_keeps_a_pickup_without_dependent_orders_in_its_slot():
  order = _order_stop(1, slot=MORNING)
  cp = _cp_stop(10, slot=NOON)

  groups = _group_by_slot([order], [cp], dependencies={})

  assert groups == [([order], []), ([], [cp])]


# ---------------------------------------------------------------------------
# _sequence_slot
# ---------------------------------------------------------------------------

DEPOT = (41.10, 16.80)
NEAR = (41.11, 16.80)
FAR = (41.40, 16.80)


def _slot_matrix(stops, start=None):
  located = [stop for stop in stops if stop.coord is not None]
  offset = 1 if start else 0
  matrix = duration_matrix(([start] if start else []) + [stop.coord for stop in located])
  return matrix, {stop.item.id: offset + position for position, stop in enumerate(located)}


def test_sequence_slot_starts_from_the_vehicle_position():
  far, near = _order_stop(1, coord=FAR), _order_stop(2, coord=NEAR)
  matrix, index = _slot_matrix([far, near], start=DEPOT)

  assert _sequence_slot([far, near], [], {}, matrix, index, start=0) == [near, far]


def test_sequence_slot_visits_an_independent_order_on_the_way_to_the_pickup_deliveries():
  # Il ritiro e' vicino al deposito, la sua consegna lontana; l'ordine senza
  # ritiri sta a meta' strada: si fa andando, non dopo essere tornati indietro.
  pickup = _cp_stop(10, coord=(41.11, 16.80))
  independent = _order_stop(1, coord=(41.25, 16.80))
  delivery = _order_stop(2, coord=FAR)
  stops = [pickup, independent, delivery]
  matrix, index = _slot_matrix(stops, start=DEPOT)

  sequence = _sequence_slot([independent, delivery], [pickup], {delivery.item.id: {10}}, matrix, index, start=0)

  assert sequence == [pickup, independent, delivery]


def test_sequence_slot_never_delivers_before_the_pickup():
  # La consegna e' accanto al deposito, il ritiro lontano: tocca andare al ritiro e tornare.
  pickup = _cp_stop(10, coord=FAR)
  delivery = _order_stop(1, coord=NEAR)
  matrix, index = _slot_matrix([pickup, delivery], start=DEPOT)

  sequence = _sequence_slot([delivery], [pickup], {delivery.item.id: {10}}, matrix, index, start=0)

  assert sequence == [pickup, delivery]


def test_sequence_slot_keeps_unlocated_pickups_first_and_unlocated_deliveries_last():
  pickup = _cp_stop(10, coord=None)
  located = _order_stop(1, coord=NEAR)
  unlocated = _order_stop(2, coord=None)
  matrix, index = _slot_matrix([pickup, located, unlocated], start=DEPOT)

  sequence = _sequence_slot([unlocated, located], [pickup], {located.item.id: {10}}, matrix, index, start=0)

  assert sequence == [pickup, located, unlocated]

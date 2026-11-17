from itertools import permutations
from unittest.mock import patch

from src.schedulation.sequencing import (
  duration_matrix,
  respects_precedence,
  route_cost,
  sequence_schedule_items,
  sequence_stops,
  transport_start_coord,
)

from tests.unit.schedulation.conftest import make_order


def _line_matrix(positions):
  """Tappe su una retta: la durata e' la distanza tra le posizioni."""
  return [[abs(a - b) for b in positions] for a in positions]


def _best_cost(matrix, stops, start, predecessors):
  return min(
    route_cost(matrix, list(route), start)
    for route in permutations(stops)
    if respects_precedence(list(route), predecessors)
  )


# ---------------------------------------------------------------------------
# sequence_stops
# ---------------------------------------------------------------------------


def test_sequence_stops_goes_out_from_the_start_without_zigzag():
  # Partenza in 0, tappe arrivate alla rinfusa: si visitano andando dritti.
  matrix = _line_matrix([0, 5, 1, 4, 2, 3])

  assert sequence_stops(matrix, [1, 2, 3, 4, 5], start=0) == [2, 4, 5, 3, 1]


def test_sequence_stops_keeps_same_place_stops_together():
  # Due ordini nello stesso CAP (stessa posizione) e uno in mezzo arrivato tra loro.
  matrix = _line_matrix([0, 10, 3, 10])

  route = sequence_stops(matrix, [1, 2, 3], start=0)

  assert abs(route.index(1) - route.index(3)) == 1


def test_sequence_stops_puts_the_pickup_before_its_delivery():
  # Consegna (1) accanto alla partenza, ritiro (2) lontano.
  matrix = _line_matrix([0, 1, 10])

  assert sequence_stops(matrix, [1, 2], start=0, predecessors={1: {2}}) == [2, 1]


def test_sequence_stops_ignores_pickups_outside_the_stops():
  # Il ritiro 9 e' di una fascia prima: gia' fatto, non vincola.
  matrix = _line_matrix([0, 1, 2])

  assert sequence_stops(matrix, [2, 1], start=0, predecessors={1: {9}}) == [1, 2]


def test_sequence_stops_without_start_picks_the_best_end_to_start_from():
  matrix = _line_matrix([3, 0, 2, 1])

  route = sequence_stops(matrix, [0, 1, 2, 3])

  assert route_cost(matrix, route) == 3


def test_sequence_stops_matches_the_exhaustive_optimum_on_small_rounds():
  positions = [(0, 0), (4, 1), (1, 3), (5, 5), (2, 2), (6, 0), (3, 4)]
  matrix = [[abs(a[0] - b[0]) + abs(a[1] - b[1]) for b in positions] for a in positions]
  stops = [1, 2, 3, 4, 5, 6]
  predecessors = {3: {5}, 2: {5}}

  route = sequence_stops(matrix, stops, start=0, predecessors=predecessors)

  assert respects_precedence(route, predecessors)
  assert route_cost(matrix, route, 0) == _best_cost(matrix, stops, 0, predecessors)


def test_sequence_stops_with_one_stop_or_none():
  assert sequence_stops([[0]], [], start=None) == []
  assert sequence_stops([[0, 1], [1, 0]], [1], start=0) == [1]


# ---------------------------------------------------------------------------
# duration_matrix
# ---------------------------------------------------------------------------


@patch('src.schedulation.sequencing.travel_time_matrix_osrm', return_value=[[0, 7], [9, 0]])
def test_duration_matrix_uses_osrm(mock_osrm):
  assert duration_matrix([(41.0, 16.0), (41.1, 16.0)]) == [[0, 7], [9, 0]]


@patch('src.schedulation.sequencing.travel_time_matrix_osrm', return_value=None)
def test_duration_matrix_falls_back_to_straight_line_when_osrm_is_down(mock_osrm):
  matrix = duration_matrix([(41.0, 16.0), (41.1, 16.0), (41.3, 16.0)])

  assert matrix[0][0] == 0
  assert 0 < matrix[0][1] < matrix[0][2]


# ---------------------------------------------------------------------------
# Proposte borderò
# ---------------------------------------------------------------------------


def _items(*orders):
  from src.schedulation.building import build_schedule_items

  return build_schedule_items(list(orders))


def test_sequence_schedule_items_orders_deliveries_from_the_depot():
  # Bari centro (70121) accanto al deposito, Molfetta (70056) lontana: arrivati al contrario.
  items = _items(make_order(1, '70056', collection_point_id=10), make_order(2, '70121', collection_point_id=10))
  items[0]['cap'] = '70122'  # il ritiro a Bari, accanto al deposito

  sequenced = sequence_schedule_items(items, start=(41.1239663, 16.8665147))

  assert [item.get('order_id') for item in sequenced] == [None, 2, 1]
  assert [item['index'] for item in sequenced] == [0, 1, 2]


def test_sequence_schedule_items_keeps_all_pickups_before_deliveries():
  # La consegna 1 e' accanto al deposito, i ritiri lontani: la proposta li mostra comunque per primi.
  items = _items(make_order(1, '70121', collection_point_id=10), make_order(2, '70056', collection_point_id=20))
  for item in items:
    if item['operation_type'] == 'CollectionPoint':
      item['cap'] = '70056'

  sequenced = sequence_schedule_items(items, start=(41.1201889, 16.8753662))

  assert [item['operation_type'] for item in sequenced] == ['CollectionPoint', 'CollectionPoint', 'Order', 'Order']


def test_sequence_schedule_items_leaves_unlocated_deliveries_at_the_end():
  items = _items(make_order(1, '99999', collection_point_id=10), make_order(2, '70121', collection_point_id=10))

  sequenced = sequence_schedule_items(items)

  assert [item.get('order_id') for item in sequenced] == [None, 2, 1]


def test_transport_start_coord_needs_an_address_or_a_cap():
  assert transport_start_coord(None) is None
  assert transport_start_coord({'id': 1, 'address': None, 'cap': None}) is None
  assert transport_start_coord({'id': 1, 'cap': '70121'}) == (41.1201889, 16.8753662)


def test_sequence_stops_on_large_rounds_respects_pickups_and_beats_the_nearest_neighbour():
  # Oltre la soglia del giro esatto: euristica, ma mai peggio della sola costruzione.
  from src.schedulation.sequencing import _nearest_neighbour

  positions = [(0, 0)] + [((i * 37) % 23, (i * 53) % 19) for i in range(1, 16)]
  matrix = [[abs(a[0] - b[0]) + abs(a[1] - b[1]) for b in positions] for a in positions]
  stops = list(range(1, 16))
  predecessors = {4: {9}, 7: {9}, 12: {2}}

  route = sequence_stops(matrix, stops, start=0, predecessors=predecessors)

  assert sorted(route) == stops
  assert respects_precedence(route, predecessors)
  baseline = _nearest_neighbour(matrix, stops, 0, predecessors)
  assert route_cost(matrix, route, 0) <= route_cost(matrix, baseline, 0)

from unittest.mock import patch

from geopy.distance import geodesic

from src.end_points.service import travel
from src.end_points.service.travel import (
  _FALLBACK_SPEED_KMH,
  calculate_travel_overhead_minutes,
  sequential_travel_minutes,
  travel_time_matrix_osrm,
  trip_order_osrm,
)

from tests.unit.factories import create_order


def _osrm_response(status_code=200, code='Ok', durations=None):
  mock_response = type('MockResponse', (), {})()
  mock_response.status_code = status_code
  mock_response.json = lambda: {'code': code, 'durations': durations}
  return mock_response


BARI = (41.1171, 16.8719)
MOLFETTA = (41.2016, 16.6008)


def test_osrm_urls_are_built_on_the_configured_base_url():
  base = travel.OSRM_BASE_URL
  assert travel._OSRM_TABLE_URL.startswith(f'{base}/table/v1/driving/')
  assert travel._OSRM_TRIP_URL.startswith(f'{base}/trip/v1/driving/')


def test_travel_time_matrix_osrm_returns_none_with_fewer_than_two_coords():
  assert travel_time_matrix_osrm([BARI]) is None


@patch('src.end_points.service.travel.requests.get')
def test_travel_time_matrix_osrm_returns_durations_on_success(mock_get):
  mock_get.return_value = _osrm_response(durations=[[0, 600], [600, 0]])

  assert travel_time_matrix_osrm([BARI, MOLFETTA]) == [[0, 600], [600, 0]]


@patch('src.end_points.service.travel.requests.get')
def test_travel_time_matrix_osrm_returns_none_when_osrm_unavailable(mock_get):
  mock_get.side_effect = Exception('timeout')

  assert travel_time_matrix_osrm([BARI, MOLFETTA]) is None


@patch('src.end_points.service.travel.requests.get')
def test_travel_time_matrix_osrm_returns_none_on_non_ok_code(mock_get):
  mock_get.return_value = _osrm_response(code='NoRoute', durations=None)

  assert travel_time_matrix_osrm([BARI, MOLFETTA]) is None


def test_sequential_travel_minutes_with_fewer_than_two_coords_is_zero():
  assert sequential_travel_minutes([]) == 0
  assert sequential_travel_minutes([BARI]) == 0


@patch('src.end_points.service.travel.travel_time_matrix_osrm')
def test_sequential_travel_minutes_uses_osrm_matrix(mock_matrix):
  mock_matrix.return_value = [[0, 600, 900], [600, 0, 300], [900, 300, 0]]

  assert sequential_travel_minutes([BARI, MOLFETTA, BARI]) == 15  # (600 + 300) / 60


@patch('src.end_points.service.travel.travel_time_matrix_osrm')
def test_sequential_travel_minutes_falls_back_to_haversine_when_osrm_fails(mock_matrix):
  mock_matrix.return_value = None
  expected = round(geodesic(BARI, MOLFETTA).kilometers / _FALLBACK_SPEED_KMH * 60)

  assert sequential_travel_minutes([BARI, MOLFETTA]) == expected
  assert expected > 0


def test_calculate_travel_overhead_minutes_without_existing_orders_is_zero():
  assert calculate_travel_overhead_minutes([], '70020') == 0


def test_calculate_travel_overhead_minutes_without_new_cap_is_zero():
  order = create_order(cap='70020')

  assert calculate_travel_overhead_minutes([order], '') == 0


@patch('src.end_points.service.travel.get_lat_lon_by_cap')
def test_calculate_travel_overhead_minutes_is_zero_when_new_cap_unresolvable(mock_geocode):
  mock_geocode.return_value = (None, None)
  order = create_order(cap='70020')

  assert calculate_travel_overhead_minutes([order], '99999') == 0


@patch('src.end_points.service.travel.get_lat_lon_by_address')
@patch('src.end_points.service.travel.get_lat_lon_by_cap')
def test_calculate_travel_overhead_minutes_is_zero_when_no_existing_cap_resolves(mock_geocode, mock_geocode_address):
  # L'indirizzo dell'ordine esistente non risolve mai: forza il fallback al CAP,
  # che è quello che questo test vuole verificare.
  mock_geocode_address.return_value = (None, None)

  def fake_geocode(cap):
    return (None, None) if cap == '70020' else BARI

  mock_geocode.side_effect = fake_geocode
  order = create_order(cap='70020')

  assert calculate_travel_overhead_minutes([order], '70056') == 0


@patch('src.end_points.service.travel.sequential_travel_minutes')
@patch('src.end_points.service.travel.get_lat_lon_by_address')
@patch('src.end_points.service.travel.get_lat_lon_by_cap')
def test_calculate_travel_overhead_minutes_returns_the_added_delta(mock_geocode, mock_geocode_address, mock_sequential):
  # L'indirizzo non risolve: il test verifica il percorso via CAP (coords_by_cap).
  mock_geocode_address.return_value = (None, None)
  coords_by_cap = {'70020': BARI, '70056': MOLFETTA}
  mock_geocode.side_effect = lambda cap: coords_by_cap[cap]
  # baseline (solo l'esistente): 10 min. Con il nuovo ordine aggiunto: 25 min.
  mock_sequential.side_effect = lambda coords: 10 if len(coords) == 1 else 25
  order = create_order(cap='70020')

  assert calculate_travel_overhead_minutes([order], '70056') == 15


@patch('src.end_points.service.travel.sequential_travel_minutes')
@patch('src.end_points.service.travel.get_lat_lon_by_address')
@patch('src.end_points.service.travel.get_lat_lon_by_cap')
def test_calculate_travel_overhead_minutes_never_negative(mock_geocode, mock_geocode_address, mock_sequential):
  mock_geocode_address.return_value = (None, None)
  mock_geocode.return_value = BARI
  # Il nuovo ordine "accorcia" il percorso sequenziale: l'overhead resta 0, non negativo.
  mock_sequential.side_effect = lambda coords: 30 if len(coords) == 1 else 20
  order = create_order(cap='70020')

  assert calculate_travel_overhead_minutes([order], '70056') == 0


def _trip_response(waypoint_indices, leg_durations, code='Ok'):
  mock_response = type('MockResponse', (), {})()
  mock_response.status_code = 200
  mock_response.json = lambda: {
    'code': code,
    'waypoints': [{'waypoint_index': i} for i in waypoint_indices],
    'trips': [{'legs': [{'duration': d} for d in leg_durations]}],
  }
  return mock_response


def test_trip_order_osrm_asks_for_a_closed_tour():
  # roundtrip=false con source=any&destination=any non e' supportato da OSRM
  assert 'roundtrip=true' in travel._OSRM_TRIP_URL


@patch('src.end_points.service.travel.requests.get')
def test_trip_order_osrm_opens_the_cycle_at_the_longest_leg(mock_get):
  # giro 1 -> 2 -> 0 (poi torna a 1): il tratto piu' lungo e' il ritorno 0 -> 1,
  # quindi il percorso aperto parte da 1
  mock_get.return_value = _trip_response(waypoint_indices=[2, 0, 1], leg_durations=[100, 200, 900])
  assert trip_order_osrm([BARI, MOLFETTA, BARI]) == [1, 2, 0]


@patch('src.end_points.service.travel.requests.get')
def test_trip_order_osrm_keeps_the_order_when_the_longest_leg_is_the_return(mock_get):
  mock_get.return_value = _trip_response(waypoint_indices=[0, 1, 2], leg_durations=[100, 200, 900])
  assert trip_order_osrm([BARI, MOLFETTA, BARI]) == [0, 1, 2]


@patch('src.end_points.service.travel.requests.get')
def test_trip_order_osrm_returns_none_on_non_ok_code(mock_get):
  mock_get.return_value = _trip_response([0, 1], [1, 1], code='NoTrips')
  assert trip_order_osrm([BARI, MOLFETTA]) is None


@patch('src.end_points.service.travel.requests.get', side_effect=Exception('boom'))
def test_trip_order_osrm_returns_none_when_osrm_unavailable(mock_get):
  assert trip_order_osrm([BARI, MOLFETTA]) is None


# ---------------------------------------------------------------------------
# Strada in testa alla giornata: veicolo -> ritiri -> prima consegna
# ---------------------------------------------------------------------------

BISCEGLIE = (41.2428, 16.5053)
TRANI = (41.2769, 16.4172)
BARLETTA = (41.3197, 16.2836)
FOGGIA = (41.4622, 15.5446)


@patch('src.end_points.service.travel.sequential_travel_minutes', return_value=42)
def test_front_route_visits_pickups_nearest_first_then_the_delivery_closest_to_the_last(mock_sequential):
  # Il veicolo sta a Bisceglie: dei due ritiri passa prima da Trani (piu' vicino),
  # poi da Foggia; dopo Foggia va verso la consegna che le e' piu' vicina, Barletta.
  minutes = travel.front_route_minutes(BISCEGLIE, pickups=[FOGGIA, TRANI], deliveries=[BARI, BARLETTA])

  assert minutes == 42
  assert mock_sequential.call_args.args[0] == [BISCEGLIE, TRANI, FOGGIA, BARLETTA]


@patch('src.end_points.service.travel.sequential_travel_minutes', return_value=10)
def test_front_route_without_pickups_goes_straight_to_the_nearest_delivery(mock_sequential):
  travel.front_route_minutes(BISCEGLIE, pickups=[], deliveries=[BARI, TRANI])

  assert mock_sequential.call_args.args[0] == [BISCEGLIE, TRANI]


@patch('src.end_points.service.travel.sequential_travel_minutes', return_value=10)
def test_front_route_without_deliveries_ends_at_the_last_pickup(mock_sequential):
  travel.front_route_minutes(BISCEGLIE, pickups=[TRANI], deliveries=[])

  assert mock_sequential.call_args.args[0] == [BISCEGLIE, TRANI]


def test_front_route_is_zero_when_there_is_nothing_to_reach():
  # Il solo veicolo non e' un percorso: niente chiamata a OSRM, niente minuti.
  with patch('src.end_points.service.travel.travel_time_matrix_osrm') as mock_osrm:
    assert travel.front_route_minutes(BISCEGLIE, pickups=[], deliveries=[]) == 0
  mock_osrm.assert_not_called()


@patch('src.end_points.service.travel.sequential_travel_minutes', return_value=10)
def test_front_route_keeps_two_pickups_at_the_same_place(mock_sequential):
  # Due punti di ritiro sullo stesso indirizzo non si perdono per strada.
  travel.front_route_minutes(BISCEGLIE, pickups=[TRANI, TRANI], deliveries=[])

  assert mock_sequential.call_args.args[0] == [BISCEGLIE, TRANI, TRANI]


def test_lat_lon_for_transport_falls_back_to_the_cap_when_the_address_is_not_found():
  transport = type('T', (), {'address': 'Via Sconosciuta 1', 'cap': '76011'})()
  with (
    patch('src.end_points.service.travel.get_lat_lon_by_address', return_value=(None, None)),
    patch('src.end_points.service.travel.get_lat_lon_by_cap', return_value=BISCEGLIE) as mock_cap,
  ):
    assert travel.get_lat_lon_for_transport(transport) == BISCEGLIE
  mock_cap.assert_called_once_with('76011')


def test_lat_lon_for_transport_does_not_call_the_geocoder_without_address_or_cap():
  transport = type('T', (), {'address': None, 'cap': None})()
  with (
    patch('src.end_points.service.travel.get_lat_lon_by_address') as mock_address,
    patch('src.end_points.service.travel.get_lat_lon_by_cap') as mock_cap,
  ):
    assert travel.get_lat_lon_for_transport(transport) == (None, None)
  mock_address.assert_not_called()
  mock_cap.assert_not_called()


def test_lat_lon_for_order_without_an_address_uses_the_cap():
  order = type('O', (), {'address': None, 'cap': '70051'})()
  with (
    patch('src.end_points.service.travel.get_lat_lon_by_address') as mock_address,
    patch('src.end_points.service.travel.get_lat_lon_by_cap', return_value=BARI) as mock_cap,
  ):
    assert travel.get_lat_lon_for_order(order) == BARI
  mock_address.assert_not_called()
  mock_cap.assert_called_once_with('70051')


def test_lat_lon_for_a_missing_entity_is_empty():
  assert travel.get_lat_lon_for_transport(None) == (None, None)
  assert travel.get_lat_lon_for_collection_point(None) == (None, None)


def test_lat_lon_for_collection_point_uses_the_address_first():
  point = type('P', (), {'address': 'Via Magazzino 1, Molfetta', 'cap': '70056'})()
  with (
    patch('src.end_points.service.travel.get_lat_lon_by_address', return_value=MOLFETTA),
    patch('src.end_points.service.travel.get_lat_lon_by_cap') as mock_cap,
  ):
    assert travel.get_lat_lon_for_collection_point(point) == MOLFETTA
  mock_cap.assert_not_called()


@patch('src.end_points.service.travel.requests.get')
def test_travel_time_matrix_osrm_asks_once_for_the_same_route(mock_get):
  mock_get.return_value = _osrm_response(durations=[[0, 600], [600, 0]])

  assert travel_time_matrix_osrm([BARI, MOLFETTA]) == [[0, 600], [600, 0]]
  assert travel_time_matrix_osrm([BARI, MOLFETTA]) == [[0, 600], [600, 0]]

  assert mock_get.call_count == 1


@patch('src.end_points.service.travel.requests.get')
def test_travel_time_matrix_osrm_does_not_cache_a_failure(mock_get):
  mock_get.return_value = _osrm_response(status_code=500)
  assert travel_time_matrix_osrm([BARI, MOLFETTA]) is None

  mock_get.return_value = _osrm_response(durations=[[0, 600], [600, 0]])
  assert travel_time_matrix_osrm([BARI, MOLFETTA]) == [[0, 600], [600, 0]]

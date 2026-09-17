from unittest.mock import patch

from geopy.distance import geodesic

from src.end_points.service.travel import (
  _FALLBACK_SPEED_KMH,
  calculate_travel_overhead_minutes,
  sequential_travel_minutes,
  travel_time_matrix_osrm,
)

from tests.unit.factories import create_order


def _osrm_response(status_code=200, code='Ok', durations=None):
  mock_response = type('MockResponse', (), {})()
  mock_response.status_code = status_code
  mock_response.json = lambda: {'code': code, 'durations': durations}
  return mock_response


BARI = (41.1171, 16.8719)
MOLFETTA = (41.2016, 16.6008)


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

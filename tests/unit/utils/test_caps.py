from unittest.mock import patch

import pytest

from src.utils.caps import get_cap_by_name, get_lat_lon_by_cap, get_province_by_cap


def _nominatim_response(results):
  mock_response = type('MockResponse', (), {})()
  mock_response.json = lambda: results
  mock_response.raise_for_status = lambda: None
  return mock_response


def _address_result(**address):
  return {'lat': '41.1256', 'lon': '16.8698', 'address': address}


@patch('src.utils.caps.requests.get')
def test_get_province_by_cap_finds_province(mock_get):
  mock_get.return_value = _nominatim_response([_address_result(county='Bari', postcode='70020')])

  assert get_province_by_cap('70020') == 'Bari'
  assert mock_get.call_args.kwargs['params']['postalcode'] == '70020'


@patch('src.utils.caps.requests.get')
def test_get_province_by_cap_raises_when_no_result(mock_get):
  mock_get.return_value = _nominatim_response([])

  with pytest.raises(ValueError, match='CAP 00000 not found'):
    get_province_by_cap('00000')


@patch('src.utils.caps.requests.get')
def test_get_cap_by_name_returns_postcode(mock_get):
  mock_get.return_value = _nominatim_response([_address_result(county='Bari', postcode='70056')])

  assert get_cap_by_name('Molfetta') == '70056'
  assert mock_get.call_args.kwargs['params']['city'] == 'Molfetta'


@patch('src.utils.caps.requests.get')
def test_get_cap_by_name_raises_for_unknown_city(mock_get):
  mock_get.return_value = _nominatim_response([])

  with pytest.raises(ValueError, match='not found in any CAP'):
    get_cap_by_name('Atlantide')


@patch('src.utils.caps.requests.get')
def test_get_lat_lon_by_cap_returns_coordinates(mock_get):
  mock_get.return_value = _nominatim_response([{'lat': '41.1766334', 'lon': '16.5701927', 'address': {}}])

  lat, lon = get_lat_lon_by_cap('70056')

  assert lat == pytest.approx(41.1766334)
  assert lon == pytest.approx(16.5701927)


@patch('src.utils.caps.requests.get')
def test_get_lat_lon_by_cap_returns_none_when_unresolvable(mock_get):
  mock_get.return_value = _nominatim_response([])

  assert get_lat_lon_by_cap('99999') == (None, None)

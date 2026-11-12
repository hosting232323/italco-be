from unittest.mock import patch

import pytest

from src.utils.caps import (
  NOMINATIM_REVERSE_URL,
  get_cap_by_name,
  get_lat_lon_by_address,
  get_lat_lon_by_cap,
  get_province_by_cap,
)


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
def test_get_cap_by_name_uses_reverse_geocoding_for_multi_cap_city(mock_get):
  mock_get.side_effect = [
    _nominatim_response([_address_result(city='Bari', county='Bari', state='Puglia')]),
    _nominatim_response({'address': {'city': 'Bari', 'postcode': '70122'}}),
  ]

  assert get_cap_by_name('BARI') == '70122'
  reverse_call = mock_get.call_args_list[1]
  assert reverse_call.args[0] == NOMINATIM_REVERSE_URL
  assert reverse_call.kwargs['params']['lat'] == '41.1256'
  assert reverse_call.kwargs['params']['lon'] == '16.8698'


@patch('src.utils.caps.requests.get')
def test_get_cap_by_name_raises_when_reverse_geocoding_has_no_postcode(mock_get):
  mock_get.side_effect = [
    _nominatim_response([_address_result(city='Napoli')]),
    _nominatim_response({'error': 'Unable to geocode'}),
  ]

  with pytest.raises(ValueError, match='not found in any CAP'):
    get_cap_by_name('Napoli')


@patch('src.utils.caps.requests.get')
def test_get_cap_by_name_falls_back_to_known_city_caps(mock_get):
  mock_get.side_effect = [
    _nominatim_response([_address_result(city='Cassano delle Murge', county='Bari')]),
    _nominatim_response({'address': {'town': 'Cassano delle Murge'}}),
  ]

  assert get_cap_by_name('CASSANO DELLE MURGE') == '70020'


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


@patch('src.utils.caps.requests.get')
def test_get_lat_lon_by_address_returns_coordinates(mock_get):
  mock_get.return_value = _nominatim_response([{'lat': '41.2016', 'lon': '16.6008', 'address': {}}])

  lat, lon = get_lat_lon_by_address('Via Andrea Doria, 15, Molfetta, BA')

  assert lat == pytest.approx(41.2016)
  assert lon == pytest.approx(16.6008)
  assert mock_get.call_args.kwargs['params']['q'] == 'Via Andrea Doria, 15, Molfetta, BA'


@patch('src.utils.caps.requests.get')
def test_get_lat_lon_by_address_returns_none_when_unresolvable(mock_get):
  mock_get.return_value = _nominatim_response([])

  assert get_lat_lon_by_address('Via Inesistente 0, Nessundove') == (None, None)


@patch('src.utils.caps.requests.get')
def test_lat_lon_by_address_degrades_when_the_geocoder_is_down_and_does_not_cache_the_failure(mock_get):
  import requests

  mock_get.side_effect = requests.ConnectionError('giù')
  assert get_lat_lon_by_address('Via Roma 1, Bari') == (None, None)

  mock_get.side_effect = None
  mock_get.return_value = _nominatim_response([_address_result(county='Bari')])
  assert get_lat_lon_by_address('Via Roma 1, Bari') == (41.1256, 16.8698)


@patch('src.utils.caps.requests.get')
def test_lat_lon_by_cap_degrades_when_the_geocoder_is_down(mock_get):
  import requests

  mock_get.side_effect = requests.Timeout('lento')
  assert get_lat_lon_by_cap('70121') == (None, None)


@patch('src.utils.caps.requests.get')
def test_get_lat_lon_by_address_falls_back_to_the_street_without_house_number(mock_get):
  # Google chiama la via "Via Ludovico Ariosto", OpenStreetMap "Via Ariosto":
  # l'indirizzo intero non si trova, la via senza civico nel comune nemmeno,
  # il comune sì.
  mock_get.side_effect = [
    _nominatim_response([]),
    _nominatim_response([]),
    _nominatim_response([{'lat': '40.5597', 'lon': '17.8085', 'address': {}}]),
  ]

  assert get_lat_lon_by_address('Via Ludovico Ariosto, 14, Mesagne, BR') == (40.5597, 17.8085)
  searches = [call.kwargs['params'] for call in mock_get.call_args_list]
  assert (searches[1]['street'], searches[1]['city']) == ('Via Ludovico Ariosto', 'Mesagne')
  assert searches[2]['city'] == 'Mesagne' and 'street' not in searches[2]


@patch('src.utils.caps.requests.get')
def test_get_lat_lon_by_address_strips_a_house_number_attached_to_the_street(mock_get):
  mock_get.side_effect = [
    _nominatim_response([]),
    _nominatim_response([{'lat': '41.1203', 'lon': '16.8722', 'address': {}}]),
  ]

  assert get_lat_lon_by_address('Corso Italia43/c, BARI, BA') == (41.1203, 16.8722)
  assert mock_get.call_args.kwargs['params']['street'] == 'Corso Italia'


@patch('src.utils.caps.requests.get')
def test_get_lat_lon_by_address_without_town_has_no_fallback(mock_get):
  mock_get.return_value = _nominatim_response([])

  assert get_lat_lon_by_address('Mesagne') == (None, None)
  assert mock_get.call_count == 1


@patch('src.utils.caps.requests.get')
def test_get_lat_lon_by_address_searches_the_street_in_the_cap_first(mock_get):
  # "Via Cesare Battisti" esiste in molti comuni della provincia di Taranto: la
  # ricerca libera trova Ginosa, quella nel CAP trova Taranto.
  mock_get.return_value = _nominatim_response([{'lat': '40.4665', 'lon': '17.2561', 'address': {}}])

  assert get_lat_lon_by_address('Via Cesare Battisti, 742, Taranto, TA', '74121') == (40.4665, 17.2561)
  assert mock_get.call_count == 1
  params = mock_get.call_args.kwargs['params']
  assert (params['street'], params['postalcode']) == ('Via Cesare Battisti', '74121')


@patch('src.utils.caps.requests.get')
def test_get_lat_lon_by_address_discards_a_free_text_match_in_another_cap(mock_get):
  ginosa = {'lat': '40.5781', 'lon': '16.7582', 'address': {'postcode': '74013'}}
  taranto = {'lat': '40.4600', 'lon': '17.2500', 'address': {'postcode': '74121'}}
  mock_get.side_effect = [
    _nominatim_response([]),  # via nel CAP: non trovata
    _nominatim_response([ginosa, taranto]),  # ricerca libera
  ]

  assert get_lat_lon_by_address('Via Cesare Battisti, 742, Taranto, TA', '74121') == (40.46, 17.25)


@patch('src.utils.caps.requests.get')
def test_get_lat_lon_by_address_keeps_the_town_fallback_whatever_its_cap(mock_get):
  # Bari ha molti CAP: il ripiego sul comune non si scarta perche' ne ha un altro.
  bari = {'lat': '41.1256', 'lon': '16.8698', 'address': {'postcode': '70121'}}
  mock_get.side_effect = [
    _nominatim_response([]),
    _nominatim_response([]),
    _nominatim_response([]),
    _nominatim_response([bari]),
  ]

  assert get_lat_lon_by_address('Via Inesistente, 3, Bari, BA', '70125') == (41.1256, 16.8698)


@patch('src.utils.caps.requests.get')
def test_get_lat_lon_by_address_without_cap_keeps_the_free_text_search_first(mock_get):
  mock_get.return_value = _nominatim_response([{'lat': '41.2016', 'lon': '16.6008', 'address': {'postcode': '70056'}}])

  assert get_lat_lon_by_address('Via Andrea Doria, 15, Molfetta, BA') == (41.2016, 16.6008)
  assert 'q' in mock_get.call_args.kwargs['params']

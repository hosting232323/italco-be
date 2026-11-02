from unittest.mock import patch

import requests
from database_api.operations import get_by_id

from src.database.enum import UserRole
from src.database.schema import CollectionPoint
from src.end_points.collection_point import query_collection_points, query_collection_points_available

from tests.unit.factories import (
  auth_header,
  create_collection_point,
  create_order,
  create_product,
  create_user,
  customer_with_service,
)


def test_create_collection_point_binds_to_authenticated_customer(client):
  customer = create_user(UserRole.CUSTOMER)

  response = client.post(
    '/collection-point',
    json={'name': 'Magazzino', 'address': 'Via X 1', 'cap': '70020'},
    headers=auth_header(customer),
  )

  body = response.get_json()
  assert body['status'] == 'ok'
  assert body['collection_point']['user_id'] == customer.id


def test_get_collection_points_customer_sees_only_own(client):
  customer = create_user(UserRole.CUSTOMER)
  own = create_collection_point(customer)
  other_customer = create_user(UserRole.CUSTOMER)
  create_collection_point(other_customer)

  response = client.get('/collection-point', headers=auth_header(customer))

  body = response.get_json()
  assert [cp['id'] for cp in body['collection_points']] == [own.id]


def test_get_collection_points_admin_sees_all(client):
  admin = create_user(UserRole.ADMIN)
  customer = create_user(UserRole.CUSTOMER)
  create_collection_point(customer)
  create_collection_point(customer)

  response = client.get('/collection-point', headers=auth_header(admin))

  assert len(response.get_json()['collection_points']) == 2


def test_get_collection_points_admin_filters_by_customer(client):
  admin = create_user(UserRole.ADMIN)
  customer = create_user(UserRole.CUSTOMER)
  own = create_collection_point(customer)
  create_collection_point(create_user(UserRole.CUSTOMER))

  response = client.get(f'/collection-point?user_id={customer.id}', headers=auth_header(admin))

  assert [cp['id'] for cp in response.get_json()['collection_points']] == [own.id]


def test_create_collection_point_admin_for_customer(client):
  admin = create_user(UserRole.ADMIN)
  customer = create_user(UserRole.CUSTOMER)

  response = client.post(
    '/collection-point',
    json={'name': 'Magazzino', 'address': 'Via X 1', 'cap': '70020', 'user_id': customer.id},
    headers=auth_header(admin),
  )

  assert response.get_json()['collection_point']['user_id'] == customer.id


def test_create_collection_point_customer_cannot_choose_owner(client):
  customer = create_user(UserRole.CUSTOMER)
  other = create_user(UserRole.CUSTOMER)

  response = client.post(
    '/collection-point',
    json={'name': 'Magazzino', 'address': 'Via X 1', 'cap': '70020', 'user_id': other.id},
    headers=auth_header(customer),
  )

  assert response.get_json()['collection_point']['user_id'] == customer.id


@patch('src.end_points.collection_point.get_lat_lon_by_address')
def test_get_collection_points_includes_geocoded_coordinates(mock_geocode, client):
  mock_geocode.return_value = (41.1, 16.8)
  customer = create_user(UserRole.CUSTOMER)
  create_collection_point(customer)

  response = client.get('/collection-point', headers=auth_header(customer))

  point = response.get_json()['collection_points'][0]
  assert (point['lat'], point['lon']) == (41.1, 16.8)


@patch('src.end_points.collection_point.get_lat_lon_by_address')
def test_get_collection_points_lat_lon_none_when_geocoding_fails(mock_geocode, client):
  mock_geocode.return_value = (None, None)
  customer = create_user(UserRole.CUSTOMER)
  create_collection_point(customer)

  response = client.get('/collection-point', headers=auth_header(customer))

  point = response.get_json()['collection_points'][0]
  assert (point['lat'], point['lon']) == (None, None)


@patch('src.utils.caps.requests.get', side_effect=requests.ConnectionError('giù'))
def test_get_collection_points_survives_an_unreachable_geocoder(_get, client):
  """Nominatim giù: la lista dei punti di ritiro si legge lo stesso, solo senza coordinate."""
  customer = create_user(UserRole.CUSTOMER)
  create_collection_point(customer)

  response = client.get('/collection-point', headers=auth_header(customer))

  body = response.get_json()
  assert body['status'] == 'ok'
  point = body['collection_points'][0]
  assert (point['lat'], point['lon']) == (None, None)
  assert point['name']


@patch('src.end_points.collection_point.get_lat_lon_by_address')
def test_get_collection_points_geocodes_each_point_independently(mock_geocode, client):
  """Un punto non geocodificabile non toglie le coordinate agli altri."""
  mock_geocode.side_effect = lambda address: (41.1, 16.8) if 'Trovato' in address else (None, None)
  customer = create_user(UserRole.CUSTOMER)
  create_collection_point(customer, address='Via Trovato 1, Bari')
  create_collection_point(customer, address='Via Perduta 1, Bari')

  response = client.get('/collection-point', headers=auth_header(customer))

  by_address = {point['address']: (point['lat'], point['lon']) for point in response.get_json()['collection_points']}
  assert by_address == {'Via Trovato 1, Bari': (41.1, 16.8), 'Via Perduta 1, Bari': (None, None)}


def test_update_collection_point(client):
  customer = create_user(UserRole.CUSTOMER)
  collection_point = create_collection_point(customer)

  response = client.put(
    f'/collection-point/{collection_point.id}', json={'name': 'Nuovo nome'}, headers=auth_header(customer)
  )

  assert response.get_json()['status'] == 'ok'
  assert get_by_id(CollectionPoint, collection_point.id).name == 'Nuovo nome'


def test_update_collection_point_ignores_preload_areas_sent_back_by_the_form(client):
  admin = create_user(UserRole.ADMIN)
  point = create_collection_point(create_user(UserRole.CUSTOMER))
  client.post(f'/collection-point/{point.id}/preload-area', json={'caps': ['70051']}, headers=auth_header(admin))
  listed = client.get('/collection-point', headers=auth_header(admin)).get_json()['collection_points'][0]
  assert listed['preload_areas']
  # Come il frontend: il punto intero, senza i campi gestiti dal server.
  full_point = {key: value for key, value in listed.items() if key not in ('created_at', 'updated_at', 'users')}

  response = client.put(
    f'/collection-point/{point.id}', json={**full_point, 'name': 'Rinominato'}, headers=auth_header(admin)
  )

  assert response.get_json()['status'] == 'ok'
  assert get_by_id(CollectionPoint, point.id).name == 'Rinominato'


def test_collection_point_preloaded_flag_defaults_off_and_is_editable_by_admin(client):
  admin = create_user(UserRole.ADMIN)
  customer = create_user(UserRole.CUSTOMER)

  created = client.post(
    '/collection-point',
    json={'name': 'Magazzino', 'address': 'Via X 1', 'cap': '70020', 'preloaded': True, 'user_id': customer.id},
    headers=auth_header(admin),
  ).get_json()['collection_point']
  assert created['preloaded'] is True

  collection_point = create_collection_point(customer)
  assert collection_point.preloaded is False
  client.put(f'/collection-point/{collection_point.id}', json={'preloaded': True}, headers=auth_header(admin))
  assert get_by_id(CollectionPoint, collection_point.id).preloaded is True


def test_collection_point_preloaded_flag_is_ignored_for_non_admin(client):
  customer = create_user(UserRole.CUSTOMER)
  operator = create_user(UserRole.OPERATOR)

  created = client.post(
    '/collection-point',
    json={'name': 'Magazzino', 'address': 'Via X 1', 'cap': '70020', 'preloaded': True},
    headers=auth_header(customer),
  ).get_json()['collection_point']
  assert created['preloaded'] is False

  collection_point = create_collection_point(customer)
  for user in (customer, operator):
    client.put(f'/collection-point/{collection_point.id}', json={'preloaded': True}, headers=auth_header(user))
    assert get_by_id(CollectionPoint, collection_point.id).preloaded is False


def test_collection_point_preload_cannot_be_turned_off_with_upcoming_preloaded_orders(client):
  from datetime import date, timedelta

  from database_api.operations import update

  from tests.unit.factories import create_order, create_product_row, customer_with_service

  customer, _, service_user, collection_point = customer_with_service()
  admin = create_user(UserRole.ADMIN)
  update(collection_point, {'preloaded': True})
  order = create_order(dpc=date.today() + timedelta(days=2))
  update(order, {'preloaded': True})
  create_product_row(order, service_user, collection_point_id=collection_point.id)

  blocked = client.put(
    f'/collection-point/{collection_point.id}', json={'preloaded': False}, headers=auth_header(admin)
  ).get_json()
  assert blocked['status'] == 'ko'
  assert get_by_id(CollectionPoint, collection_point.id).preloaded is True

  # Con l'ordine non piu' precaricato il flag si puo' spegnere.
  update(order, {'preloaded': False})
  allowed = client.put(
    f'/collection-point/{collection_point.id}', json={'preloaded': False}, headers=auth_header(admin)
  ).get_json()
  assert allowed['status'] == 'ok'
  assert get_by_id(CollectionPoint, collection_point.id).preloaded is False


def test_delete_collection_point(client):
  customer = create_user(UserRole.CUSTOMER)
  collection_point = create_collection_point(customer)

  response = client.delete(f'/collection-point/{collection_point.id}', headers=auth_header(customer))

  assert response.get_json()['status'] == 'ok'
  assert get_by_id(CollectionPoint, collection_point.id) is None


def test_query_collection_points_available_follows_order_products(db):
  _, _, service_user, collection_point = customer_with_service()
  order = create_order()
  create_product(order, service_user)
  # punto di ritiro di un altro cliente, non collegato all'ordine
  create_collection_point(create_user(UserRole.CUSTOMER))

  available = query_collection_points_available(order.id)

  assert [cp.id for cp in available] == [collection_point.id]


def test_query_collection_points_respects_role(db):
  customer = create_user(UserRole.CUSTOMER)
  own = create_collection_point(customer)
  admin = create_user(UserRole.ADMIN)
  other = create_collection_point(create_user(UserRole.CUSTOMER))

  assert [cp.id for cp in query_collection_points(customer)] == [own.id]
  assert {cp.id for cp in query_collection_points(admin)} == {own.id, other.id}


@patch('src.end_points.collection_point.get_lat_lon_by_address', return_value=(41.1, 16.8))
def test_coordinates_are_saved_on_the_first_read_and_not_geocoded_again(mock_geocode, client):
  customer = create_user(UserRole.CUSTOMER)
  create_collection_point(customer)

  first = client.get('/collection-point', headers=auth_header(customer)).get_json()['collection_points'][0]
  second = client.get('/collection-point', headers=auth_header(customer)).get_json()['collection_points'][0]

  assert (first['lat'], first['lon']) == (second['lat'], second['lon']) == (41.1, 16.8)
  assert mock_geocode.call_count == 1


@patch('src.end_points.collection_point.get_lat_lon_by_address', return_value=(41.1, 16.8))
def test_creating_a_collection_point_ignores_implausible_coordinates_sent(_geocode, client):
  customer = create_user(UserRole.CUSTOMER)

  response = client.post(
    '/collection-point',
    json={'name': 'Magazzino', 'address': 'Via Roma 1, Bari', 'cap': '70121', 'lat': 0.0, 'lon': 0.0},
    headers=auth_header(customer),
  )

  point = response.get_json()['collection_point']
  assert (point['lat'], point['lon']) == (41.1, 16.8)


@patch('src.end_points.collection_point.get_lat_lon_by_address')
def test_creating_a_collection_point_keeps_the_position_chosen_on_google(mock_geocode, client):
  customer = create_user(UserRole.CUSTOMER)

  response = client.post(
    '/collection-point',
    json={'name': 'Magazzino', 'address': 'Via Roma 1, Bari', 'cap': '70121', 'lat': 41.12, 'lon': 16.87},
    headers=auth_header(customer),
  )

  point = response.get_json()['collection_point']
  assert (point['lat'], point['lon']) == (41.12, 16.87)
  mock_geocode.assert_not_called()


@patch('src.end_points.collection_point.get_lat_lon_by_address', return_value=(41.1, 16.8))
def test_moving_a_collection_point_with_its_old_coordinates_geocodes_the_new_address(_geocode, client):
  # Il form rimanda il punto intero: le coordinate sono ancora quelle del vecchio indirizzo.
  customer = create_user(UserRole.CUSTOMER)
  point = create_collection_point(customer, lat=40.5, lon=17.8)

  client.put(
    f'/collection-point/{point.id}',
    json={'address': 'Via Nuova 2, Bari', 'lat': 40.5, 'lon': 17.8},
    headers=auth_header(customer),
  )

  point = get_by_id(CollectionPoint, point.id)
  assert (point.lat, point.lon) == (41.1, 16.8)


@patch('src.end_points.collection_point.get_lat_lon_by_address')
def test_correcting_a_collection_point_on_the_map_saves_the_new_position(mock_geocode, client):
  customer = create_user(UserRole.CUSTOMER)
  point = create_collection_point(customer, lat=40.5, lon=17.8)

  client.put(
    f'/collection-point/{point.id}',
    json={'address': point.address, 'lat': 40.56, 'lon': 17.81},
    headers=auth_header(customer),
  )

  point = get_by_id(CollectionPoint, point.id)
  assert (point.lat, point.lon) == (40.56, 17.81)
  mock_geocode.assert_not_called()


def test_preload_areas_are_admin_only_and_listed_with_the_point(client):
  admin = create_user(UserRole.ADMIN)
  customer = create_user(UserRole.CUSTOMER)
  point = create_collection_point(customer)
  path = f'/collection-point/{point.id}/preload-area'

  assert client.post(path, json={'caps': ['70051']}, headers=auth_header(customer)).status_code in (401, 403)

  created = client.post(path, json={'name': 'Nord', 'caps': ['70051', ' 70051 ']}, headers=auth_header(admin))
  area = created.get_json()['preload_area']
  assert area['caps'] == ['70051']
  assert area['collection_point_id'] == point.id

  listed = client.get('/collection-point', headers=auth_header(admin)).get_json()['collection_points']
  assert [a['id'] for p in listed if p['id'] == point.id for a in p['preload_areas']] == [area['id']]


def test_preload_area_needs_caps_or_polygon(client):
  admin = create_user(UserRole.ADMIN)
  point = create_collection_point(create_user(UserRole.CUSTOMER))

  response = client.post(
    f'/collection-point/{point.id}/preload-area', json={'caps': [], 'polygon': [[1, 2]]}, headers=auth_header(admin)
  )

  assert response.get_json()['status'] == 'ko'


def test_preload_area_update_and_delete(client):
  admin = create_user(UserRole.ADMIN)
  point = create_collection_point(create_user(UserRole.CUSTOMER))
  area = client.post(
    f'/collection-point/{point.id}/preload-area', json={'caps': ['70051']}, headers=auth_header(admin)
  ).get_json()['preload_area']

  polygon = [[41.0, 16.0], [41.0, 17.0], [42.0, 17.0]]
  updated = client.put(
    f'/collection-point/preload-area/{area["id"]}', json={'polygon': polygon}, headers=auth_header(admin)
  ).get_json()['preload_area']
  assert updated['polygon'] == polygon
  assert updated['caps'] == []

  client.delete(f'/collection-point/preload-area/{area["id"]}', headers=auth_header(admin))
  listed = client.get('/collection-point', headers=auth_header(admin)).get_json()['collection_points']
  assert [p['preload_areas'] for p in listed if p['id'] == point.id] == [[]]

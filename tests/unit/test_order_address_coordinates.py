"""Coordinate dell'indirizzo arrivate dal form (menu Google o mappa della correzione).

L'indirizzo scelto da Google ("Via Ludovico Ariosto, 14, Mesagne, BR") spesso
non esiste così in OpenStreetMap ("Via Ariosto"): con la sua posizione esatta
copertura, capienza e borderò non passano più da Nominatim.
"""

from datetime import date, time, timedelta
from unittest.mock import patch

import pytest
from database_api import Session
from database_api.operations import create, get_by_id, update

from src.database.enum import ScheduleType, UserRole
from src.database.schema import DeliveryCoverageEntry, Order, Schedule, ScheduleItem, ScheduleItemOrder
from src.end_points.service.travel import get_lat_lon_for_collection_point, get_lat_lon_for_order
from src.utils.caps import get_lat_lon_by_address, remember_address_coordinates
from src.utils.geo import parse_coordinates

from tests.unit.factories import auth_header, create_order, create_transport, create_user, customer_with_service


ARIOSTO = 'Via Ludovico Ariosto, 14, Mesagne, BR'
MESAGNE = (40.556, 17.803)
BRINDISI = (40.632, 17.936)
# Zona disegnata attorno a Mesagne, senza CAP: come la configura il cliente in demo.
MESAGNE_POLYGON = [[40.50, 17.75], [40.62, 17.75], [40.62, 17.87], [40.50, 17.87]]


def _nominatim_finds_nothing():
  response = type('MockResponse', (), {})()
  response.json = lambda: []
  response.raise_for_status = lambda: None
  return response


def _order_payload(service, collection_point, **extra):
  return {
    'type': 'Delivery',
    'addressee': 'Mario Rossi',
    'address': ARIOSTO,
    'cap': '72023',
    'dpc': '2026-07-20',
    'drc': '2026-07-18',
    'products': {'Lavatrice': {'services': [{'id': service.id}], 'collection_point': {'id': collection_point.id}}},
    **extra,
  }


# ---------------------------------------------------------------------------
# parse_coordinates / remember_address_coordinates
# ---------------------------------------------------------------------------


def test_parse_coordinates_accepts_a_position_in_italy():
  assert parse_coordinates('40.556', 17.803) == MESAGNE


@pytest.mark.parametrize('lat, lon', [(None, None), ('', ''), (0, 0), (51.5, -0.12), ('nord', 17.8)])
def test_parse_coordinates_rejects_missing_or_implausible_values(lat, lon):
  assert parse_coordinates(lat, lon) == (None, None)


@patch('src.utils.caps.requests.get')
def test_remembered_coordinates_win_over_the_geocoder(mock_get):
  remember_address_coordinates(ARIOSTO, *MESAGNE)

  assert get_lat_lon_by_address(ARIOSTO) == MESAGNE
  mock_get.assert_not_called()


@patch('src.utils.caps.requests.get')
def test_remember_without_coordinates_leaves_the_geocoder(mock_get):
  mock_get.return_value = _nominatim_finds_nothing()

  remember_address_coordinates(ARIOSTO, None, None)

  assert get_lat_lon_by_address(ARIOSTO) == (None, None)
  assert mock_get.called


@patch('src.utils.caps.requests.get')
def test_cache_clear_forgets_remembered_coordinates(mock_get):
  mock_get.return_value = _nominatim_finds_nothing()
  remember_address_coordinates(ARIOSTO, *MESAGNE)

  get_lat_lon_by_address.cache_clear()

  assert get_lat_lon_by_address(ARIOSTO) == (None, None)


# ---------------------------------------------------------------------------
# Coordinate salvate: lette prima di qualunque geocoding
# ---------------------------------------------------------------------------


@patch('src.end_points.service.travel.get_lat_lon_by_address')
def test_an_order_with_stored_coordinates_is_not_geocoded(mock_geocode):
  order = create_order(address=ARIOSTO, address_lat=MESAGNE[0], address_lon=MESAGNE[1])

  assert get_lat_lon_for_order(order) == MESAGNE
  mock_geocode.assert_not_called()


@patch('src.end_points.service.travel.get_lat_lon_by_address')
def test_a_collection_point_with_stored_coordinates_is_not_geocoded(mock_geocode):
  _, _, _, point = customer_with_service()
  point = update(point, {'lat': BRINDISI[0], 'lon': BRINDISI[1]})

  assert get_lat_lon_for_collection_point(point) == BRINDISI
  mock_geocode.assert_not_called()


@patch('src.schedulation.routing.trip_order_osrm')
@patch('src.schedulation.routing.get_lat_lon_by_cap', side_effect=AssertionError('niente geocoding'))
@patch('src.schedulation.routing.get_lat_lon_by_address', side_effect=AssertionError('niente geocoding'))
def test_the_schedule_is_ordered_on_the_stored_coordinates(_address, _cap, mock_trip):
  from src.schedulation.routing import optimize_schedule_stops

  mock_trip.side_effect = lambda coords: list(range(len(coords)))
  target = date.today() + timedelta(days=4)
  schedule = create(Schedule, {'date': target, 'transport_id': create_transport().id})
  for index, coords in enumerate([MESAGNE, BRINDISI]):
    order = create_order(dpc=target, address_lat=coords[0], address_lon=coords[1])
    item = create(
      ScheduleItem,
      {
        'index': index,
        'schedule_id': schedule.id,
        'operation_type': ScheduleType.ORDER,
        'start_time_slot': time(9, 0),
        'end_time_slot': time(13, 0),
      },
    )
    create(ScheduleItemOrder, {'order_id': order.id, 'schedule_item_id': item.id})

  with Session() as session:
    optimize_schedule_stops(session.get(Schedule, schedule.id), session)
    session.commit()

  assert mock_trip.call_args.args[0] == [MESAGNE, BRINDISI]


# ---------------------------------------------------------------------------
# Copertura: la posizione mandata con /check-constraints decide la zona
# ---------------------------------------------------------------------------


@patch('src.utils.caps.requests.get', side_effect=AssertionError('niente Nominatim'))
def test_check_constraints_places_the_address_with_the_coordinates_sent(_nominatim, app, offline_geo):
  from src.end_points.delivery_coverage import check_delivery_coverage_slots

  target = date.today() + timedelta(days=3)
  create(
    DeliveryCoverageEntry,
    {
      'day_of_week': target.weekday(),
      'transport_id': create_transport().id,
      'start_time': time(9, 0),
      'end_time': time(18, 0),
      'polygon': MESAGNE_POLYGON,
    },
  )
  payload = {
    'cap': '72023',
    'address': ARIOSTO,
    'address_lat': MESAGNE[0],
    'address_lon': MESAGNE[1],
    'service_duration': 30,
  }

  with app.test_request_context(json=payload):
    slots = check_delivery_coverage_slots()

  assert slots[target.strftime('%Y-%m-%d')] == [{'start': '09:00', 'end': '18:00', 'caps': []}]


# ---------------------------------------------------------------------------
# Ordine: creazione e modifica
# ---------------------------------------------------------------------------


@patch('src.end_points.orders.crud.get_lat_lon_by_address')
def test_create_order_saves_the_coordinates_sent_with_the_address(mock_geocode, client):
  customer, service, _, point = customer_with_service()
  payload = _order_payload(service, point, address_lat=MESAGNE[0], address_lon=MESAGNE[1])

  response = client.post('/order', json=payload, headers=auth_header(customer))

  order = response.get_json()['order']
  assert (order['address_lat'], order['address_lon']) == MESAGNE
  mock_geocode.assert_not_called()


@patch('src.end_points.orders.crud.get_lat_lon_by_address', return_value=(None, None))
def test_create_order_drops_implausible_coordinates(_geocode, client):
  customer, service, _, point = customer_with_service()
  payload = _order_payload(service, point, address_lat=0, address_lon=0)

  created = client.post('/order', json=payload, headers=auth_header(customer)).get_json()['order']

  order = get_by_id(Order, created['id'])
  assert (order.address_lat, order.address_lon) == (None, None)


def _put(client, order, **data):
  admin = create_user(UserRole.ADMIN)
  response = client.put(f'/order/{order.id}', json=data, headers=auth_header(admin))
  assert response.get_json()['status'] == 'ok', response.get_json()
  return get_by_id(Order, order.id)


def test_correcting_the_address_saves_its_new_coordinates(client):
  order = create_order(address=ARIOSTO, address_lat=MESAGNE[0], address_lon=MESAGNE[1])

  order = _put(client, order, address='Via Appia, 1, Brindisi, BR', address_lat=BRINDISI[0], address_lon=BRINDISI[1])

  assert (order.address_lat, order.address_lon) == BRINDISI


def test_changing_the_address_drops_the_coordinates_of_the_old_one(client):
  # Il form rimanda l'ordine intero: le coordinate sono ancora quelle salvate.
  order = create_order(address=ARIOSTO, address_lat=MESAGNE[0], address_lon=MESAGNE[1])

  order = _put(client, order, address='Via Appia, 1, Brindisi, BR', address_lat=MESAGNE[0], address_lon=MESAGNE[1])

  assert (order.address_lat, order.address_lon) == (None, None)


def test_saving_without_touching_the_address_keeps_its_coordinates(client):
  order = create_order(address=ARIOSTO, address_lat=MESAGNE[0], address_lon=MESAGNE[1])

  order = _put(client, order, address=ARIOSTO, operator_note='Citofonare')

  assert (order.address_lat, order.address_lon) == MESAGNE

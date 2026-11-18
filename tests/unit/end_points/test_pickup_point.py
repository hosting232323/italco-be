from database_api import Session
from database_api.operations import create, get_by_id

from src.database.enum import UserRole
from src.database.schema import CollectionPoint, PickupPoint
from src.end_points.pickup_point import address_key

from tests.unit.factories import auth_header, create_collection_point, create_user


def _pickup_point(**extra) -> PickupPoint:
  return create(
    PickupPoint,
    {'name': 'Magazzino', 'address': 'Via Roma 1, Bari', 'cap': '70121', 'lat': 41.1, 'lon': 16.8, **extra},
  )


def test_address_key_ignores_case_punctuation_and_word_order():
  assert address_key('Via Battisti, 99', '70026') == address_key('99 via battisti', ' 70026 ')
  assert address_key('Via Battisti 99', '70026') != address_key('Via Battisti 99', '70027')


def test_customer_creating_a_personal_point_adds_it_to_the_catalog(client):
  customer = create_user(UserRole.CUSTOMER)

  response = client.post(
    '/collection-point',
    json={'name': 'TP', 'address': 'Via Nuova 5, Bari', 'cap': '70121'},
    headers=auth_header(customer),
  )

  point = response.get_json()['collection_point']
  pickup_point = get_by_id(PickupPoint, point['pickup_point_id'])
  assert (pickup_point.name, pickup_point.address) == ('TP', 'Via Nuova 5, Bari')


def test_personal_point_with_a_known_address_joins_the_existing_catalog_entry(client):
  existing = _pickup_point()
  customer = create_user(UserRole.CUSTOMER)

  response = client.post(
    '/collection-point',
    json={'name': 'Altro nome', 'address': 'via roma, 1 bari', 'cap': '70121'},
    headers=auth_header(customer),
  )

  assert response.get_json()['collection_point']['pickup_point_id'] == existing.id
  with Session() as session:
    assert session.query(PickupPoint).count() == 1


def test_choosing_an_existing_pickup_point_copies_its_address_and_keeps_the_customer_name(client):
  pickup_point = _pickup_point()
  admin = create_user(UserRole.ADMIN)
  customer = create_user(UserRole.CUSTOMER)

  response = client.post(
    '/collection-point',
    json={'name': 'Mio nome', 'pickup_point_id': pickup_point.id, 'user_id': customer.id},
    headers=auth_header(admin),
  )

  point = response.get_json()['collection_point']
  assert point['name'] == 'Mio nome'
  assert (point['address'], point['cap'], point['lat'], point['lon']) == ('Via Roma 1, Bari', '70121', 41.1, 16.8)
  assert point['pickup_point_id'] == pickup_point.id
  assert point['user_id'] == customer.id


def test_choosing_an_unknown_pickup_point_is_refused(client):
  customer = create_user(UserRole.CUSTOMER)

  response = client.post(
    '/collection-point',
    json={'name': 'X', 'pickup_point_id': 9999},
    headers=auth_header(customer),
  )

  assert response.get_json()['status'] == 'ko'


def test_moving_a_collection_point_moves_it_to_another_catalog_entry(client):
  customer = create_user(UserRole.CUSTOMER)
  old = _pickup_point()
  point = create_collection_point(customer, pickup_point_id=old.id)

  response = client.put(
    f'/collection-point/{point.id}',
    json={'address': 'Via Diversa 9, Bari', 'cap': '70121', 'lat': 41.2, 'lon': 16.9},
    headers=auth_header(customer),
  )

  assert response.get_json()['status'] == 'ok'
  moved = get_by_id(CollectionPoint, point.id)
  assert moved.pickup_point_id != old.id
  assert get_by_id(PickupPoint, moved.pickup_point_id).address == 'Via Diversa 9, Bari'
  assert get_by_id(PickupPoint, old.id).address == 'Via Roma 1, Bari'


def test_pickup_points_listing_is_for_admin_and_operator_only(client):
  _pickup_point()

  assert client.get('/pickup-point', headers=auth_header(create_user(UserRole.CUSTOMER))).status_code == 403
  assert client.get('/pickup-point', headers=auth_header(create_user(UserRole.OPERATOR))).get_json()['status'] == 'ok'


def test_pickup_points_listing_shows_the_customers_using_each_entry(client):
  admin = create_user(UserRole.ADMIN)
  pickup_point = _pickup_point()
  first, second = create_user(UserRole.CUSTOMER), create_user(UserRole.CUSTOMER)
  create_collection_point(first, pickup_point_id=pickup_point.id)
  create_collection_point(second, pickup_point_id=pickup_point.id)

  entries = client.get('/pickup-point', headers=auth_header(admin)).get_json()['pickup_points']

  assert [entry['id'] for entry in entries] == [pickup_point.id]
  assert {customer['id'] for customer in entries[0]['customers']} == {first.id, second.id}


def test_create_pickup_point_refuses_a_duplicate_address(client):
  admin = create_user(UserRole.ADMIN)
  _pickup_point()

  response = client.post(
    '/pickup-point',
    json={'name': 'Doppione', 'address': 'Roma Via 1 Bari', 'cap': '70121'},
    headers=auth_header(admin),
  )

  assert response.get_json()['status'] == 'ko'


def test_update_pickup_point_propagates_the_address_to_linked_collection_points(client):
  admin = create_user(UserRole.ADMIN)
  pickup_point = _pickup_point()
  point = create_collection_point(create_user(UserRole.CUSTOMER), pickup_point_id=pickup_point.id)

  response = client.put(
    f'/pickup-point/{pickup_point.id}',
    json={'name': 'Magazzino', 'address': 'Via Corretta 2, Bari', 'cap': '70122', 'lat': 41.3, 'lon': 16.7},
    headers=auth_header(admin),
  )

  assert response.get_json()['status'] == 'ok'
  linked = get_by_id(CollectionPoint, point.id)
  assert (linked.address, linked.cap, linked.lat, linked.lon) == ('Via Corretta 2, Bari', '70122', 41.3, 16.7)


def test_delete_pickup_point_only_when_unused(client):
  admin = create_user(UserRole.ADMIN)
  used, unused = _pickup_point(), _pickup_point(address='Via Libera 3, Bari')
  create_collection_point(create_user(UserRole.CUSTOMER), pickup_point_id=used.id)

  assert client.delete(f'/pickup-point/{used.id}', headers=auth_header(admin)).get_json()['status'] == 'ko'
  assert client.delete(f'/pickup-point/{unused.id}', headers=auth_header(admin)).get_json()['status'] == 'ok'
  assert get_by_id(PickupPoint, unused.id) is None
  assert get_by_id(PickupPoint, used.id) is not None


def test_merge_moves_the_customers_points_to_the_target_and_removes_the_sources(client):
  admin = create_user(UserRole.ADMIN)
  target = _pickup_point()
  source = _pickup_point(address='Via Roma Uno, Bari', lat=None, lon=None)
  point = create_collection_point(create_user(UserRole.CUSTOMER), pickup_point_id=source.id)

  response = client.post(
    '/pickup-point/merge', json={'target_id': target.id, 'source_ids': [source.id]}, headers=auth_header(admin)
  )

  assert response.get_json()['status'] == 'ok'
  merged = get_by_id(CollectionPoint, point.id)
  assert (merged.pickup_point_id, merged.address, merged.lat) == (target.id, 'Via Roma 1, Bari', 41.1)
  assert get_by_id(PickupPoint, source.id) is None


def test_merge_needs_a_source_other_than_the_target(client):
  admin = create_user(UserRole.ADMIN)
  target = _pickup_point()

  response = client.post(
    '/pickup-point/merge', json={'target_id': target.id, 'source_ids': [target.id]}, headers=auth_header(admin)
  )

  assert response.get_json()['status'] == 'ko'


def test_form_sending_back_the_linked_entry_with_a_new_address_moves_the_point(client):
  customer = create_user(UserRole.CUSTOMER)
  old = _pickup_point()
  point = create_collection_point(customer, pickup_point_id=old.id)

  response = client.put(
    f'/collection-point/{point.id}',
    json={'pickup_point_id': old.id, 'address': 'Via Diversa 9, Bari', 'cap': '70121', 'lat': 41.2, 'lon': 16.9},
    headers=auth_header(customer),
  )

  assert response.get_json()['status'] == 'ok'
  assert get_by_id(CollectionPoint, point.id).pickup_point_id != old.id

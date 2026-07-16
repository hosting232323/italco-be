from datetime import date, timedelta

import pytest
from database_api.operations import create, get_by_id

from src.database.enum import UserRole
from src.database.schema import Constraint, GeographicCode, GeographicZone
from src.end_points.geographic_zone import check_geographic_zone, get_class

from tests.unit.factories import auth_header, create_order, create_user


def _zone_with(name='Bari', day_of_week=None, max_orders=5, code=None, code_type=True):
  zone = create(GeographicZone, {'name': name})
  if day_of_week is not None:
    create(Constraint, {'zone_id': zone.id, 'day_of_week': day_of_week, 'max_orders': max_orders})
  if code:
    create(GeographicCode, {'zone_id': zone.id, 'code': code, 'type': code_type})
  return zone


def test_create_geographic_zone(client):
  admin = create_user(UserRole.ADMIN)

  response = client.post('/geographic-zone', json={'name': 'Puglia Nord'}, headers=auth_header(admin))

  assert response.get_json()['status'] == 'ok'


def test_delete_geographic_zone_cascades(client):
  admin = create_user(UserRole.ADMIN)
  zone = _zone_with(day_of_week=0, code='70020')

  response = client.delete(f'/geographic-zone/{zone.id}', headers=auth_header(admin))

  assert response.get_json()['status'] == 'ok'
  assert get_by_id(GeographicZone, zone.id) is None


def test_get_geographic_zones_aggregates_codes_and_constraints(client):
  admin = create_user(UserRole.ADMIN)
  zone = create(GeographicZone, {'name': 'Aggregata'})
  create(Constraint, {'zone_id': zone.id, 'day_of_week': 0, 'max_orders': 5})
  create(Constraint, {'zone_id': zone.id, 'day_of_week': 1, 'max_orders': 3})
  create(GeographicCode, {'zone_id': zone.id, 'code': '70020', 'type': True})

  response = client.get('/geographic-zone', headers=auth_header(admin))

  body = response.get_json()
  assert body['status'] == 'ok'
  assert len(body['geographic_zones']) == 1
  assert len(body['geographic_zones'][0]['constraints']) == 2
  assert len(body['geographic_zones'][0]['codes']) == 1


def test_create_constraint_entity(client):
  admin = create_user(UserRole.ADMIN)
  zone = create(GeographicZone, {'name': 'Con vincoli'})

  response = client.post(
    '/geographic-zone/constraint',
    json={'zone_id': zone.id, 'day_of_week': 3, 'max_orders': 4},
    headers=auth_header(admin),
  )

  assert response.get_json()['status'] == 'ok'


def test_create_constraint_rejects_invalid_day(client):
  admin = create_user(UserRole.ADMIN)
  zone = create(GeographicZone, {'name': 'Vincolo errato'})

  response = client.post(
    '/geographic-zone/constraint',
    json={'zone_id': zone.id, 'day_of_week': 9, 'max_orders': 4},
    headers=auth_header(admin),
  )

  assert response.get_json() == {'status': 'ko', 'message': 'Errore generico'}


def test_create_code_entity_and_delete(client):
  admin = create_user(UserRole.ADMIN)
  zone = create(GeographicZone, {'name': 'Con codici'})

  created = client.post(
    '/geographic-zone/code',
    json={'zone_id': zone.id, 'code': '70121', 'type': True},
    headers=auth_header(admin),
  )
  code_id = created.get_json()['entity']['id']

  deleted = client.delete(f'/geographic-zone/code/{code_id}', headers=auth_header(admin))

  assert deleted.get_json()['status'] == 'ok'
  assert get_by_id(GeographicCode, code_id) is None


def test_get_class_mapping():
  assert get_class('constraint') is Constraint
  assert get_class('code') is GeographicCode
  with pytest.raises(ValueError, match='Unknown entity type'):
    get_class('other')


def test_check_geographic_zone_without_zone_returns_no_dates(app, db):
  with app.test_request_context(json={'cap': '70020'}):
    allowed = check_geographic_zone()

  assert allowed == []


def test_check_geographic_zone_allows_constraint_day_under_limit(app, db):
  target = date.today() + timedelta(days=3)
  _zone_with(name='Bari', day_of_week=target.weekday(), max_orders=2)

  with app.test_request_context(json={'cap': '70020'}):
    allowed = check_geographic_zone()

  assert target.strftime('%Y-%m-%d') in allowed
  # Solo i giorni con vincolo sono ammessi
  assert all(date.fromisoformat(day).weekday() == target.weekday() for day in allowed)


def test_check_geographic_zone_blocks_saturated_day(app, db):
  target = date.today() + timedelta(days=3)
  _zone_with(name='Bari', day_of_week=target.weekday(), max_orders=1)
  create_order(cap='70020', dpc=target)

  with app.test_request_context(json={'cap': '70020'}):
    allowed = check_geographic_zone()

  assert target.strftime('%Y-%m-%d') not in allowed


@pytest.mark.xfail(
  strict=True,
  reason=(
    'Bug sorgente: get_cap_data_by_province restituisce dict_keys (immutabile), '
    'ma check_geographic_zone chiama caps.append()/remove() quando esistono codici '
    'speciali, sollevando AttributeError.'
  ),
)
def test_check_geographic_zone_special_codes_extend_and_reduce(app, db):
  target = date.today() + timedelta(days=3)
  zone = _zone_with(name='Bari', day_of_week=target.weekday(), max_orders=1)
  # Il codice speciale aggiunge un CAP fuori provincia al conteggio
  create(GeographicCode, {'zone_id': zone.id, 'code': '00042', 'type': True})
  create_order(cap='00042', dpc=target)

  with app.test_request_context(json={'cap': '70020'}):
    allowed = check_geographic_zone()

  assert target.strftime('%Y-%m-%d') not in allowed

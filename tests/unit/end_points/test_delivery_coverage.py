from datetime import time

from database_api.operations import create, get_by_id, get_by_params

from src.database.enum import UserRole
from src.database.schema import DeliveryCoverageCap, DeliveryCoverageEntry

from tests.unit.factories import auth_header, create_transport, create_user


def _entry(transport, day_of_week=0, start='08:00:00', end='17:00:00', caps=('70051',)):
  entry = create(
    DeliveryCoverageEntry,
    {
      'day_of_week': day_of_week,
      'transport_id': transport.id,
      'start_time': time.fromisoformat(start),
      'end_time': time.fromisoformat(end),
    },
  )
  for cap in caps:
    create(DeliveryCoverageCap, {'entry_id': entry.id, 'cap': cap})
  return entry


def test_create_entry(client):
  admin = create_user(UserRole.ADMIN)
  transport = create_transport()

  response = client.post(
    '/delivery-coverage',
    json={
      'day_of_week': 0,
      'transport_id': transport.id,
      'start_time': '08:00',
      'end_time': '18:00',
      'caps': ['70051', '70052'],
    },
    headers=auth_header(admin),
  )

  body = response.get_json()
  assert body['status'] == 'ok'
  assert body['entry']['day_of_week'] == 0
  assert body['entry']['transport_id'] == transport.id
  assert body['entry']['start_time'] == '08:00:00'
  assert body['entry']['caps'] == ['70051', '70052']
  assert get_by_id(DeliveryCoverageEntry, body['entry']['id']) is not None


def test_create_entry_dedupes_caps(client):
  admin = create_user(UserRole.ADMIN)
  transport = create_transport()

  response = client.post(
    '/delivery-coverage',
    json={
      'day_of_week': 1,
      'transport_id': transport.id,
      'start_time': '08:00',
      'end_time': '18:00',
      'caps': ['70051', '70051', ' 70052 '],
    },
    headers=auth_header(admin),
  )

  assert sorted(response.get_json()['entry']['caps']) == ['70051', '70052']


def test_create_entry_rejects_invalid_day(client):
  admin = create_user(UserRole.ADMIN)
  transport = create_transport()

  response = client.post(
    '/delivery-coverage',
    json={
      'day_of_week': 9,
      'transport_id': transport.id,
      'start_time': '08:00',
      'end_time': '18:00',
      'caps': ['70051'],
    },
    headers=auth_header(admin),
  )

  assert response.get_json() == {'status': 'ko', 'message': 'Errore generico'}


def test_create_entry_rejects_missing_transport(client):
  admin = create_user(UserRole.ADMIN)

  response = client.post(
    '/delivery-coverage',
    json={'day_of_week': 0, 'transport_id': 999, 'start_time': '08:00', 'end_time': '18:00', 'caps': ['70051']},
    headers=auth_header(admin),
  )

  assert response.get_json() == {'status': 'ko', 'message': 'Veicolo non trovato'}


def test_create_entry_rejects_reversed_times(client):
  admin = create_user(UserRole.ADMIN)
  transport = create_transport()

  response = client.post(
    '/delivery-coverage',
    json={
      'day_of_week': 0,
      'transport_id': transport.id,
      'start_time': '18:00',
      'end_time': '08:00',
      'caps': ['70051'],
    },
    headers=auth_header(admin),
  )

  assert response.get_json()['status'] == 'ko'


def test_create_entry_rejects_unparsable_time(client):
  admin = create_user(UserRole.ADMIN)
  transport = create_transport()

  response = client.post(
    '/delivery-coverage',
    json={
      'day_of_week': 0,
      'transport_id': transport.id,
      'start_time': 'mezzogiorno',
      'end_time': '18:00',
      'caps': ['70051'],
    },
    headers=auth_header(admin),
  )

  assert response.get_json() == {'status': 'ko', 'message': 'Errore generico'}


def test_create_entry_rejects_empty_caps(client):
  admin = create_user(UserRole.ADMIN)
  transport = create_transport()

  response = client.post(
    '/delivery-coverage',
    json={'day_of_week': 0, 'transport_id': transport.id, 'start_time': '08:00', 'end_time': '18:00', 'caps': []},
    headers=auth_header(admin),
  )

  assert response.get_json() == {'status': 'ko', 'message': 'Seleziona almeno un CAP'}


def test_get_delivery_coverage_lists_entries_sorted(client):
  operator = create_user(UserRole.OPERATOR)
  transport = create_transport()
  _entry(transport, day_of_week=2, start='09:00:00', end='12:00:00')
  _entry(transport, day_of_week=0, start='14:00:00', end='16:00:00')
  _entry(transport, day_of_week=0, start='08:00:00', end='12:00:00')

  response = client.get('/delivery-coverage', headers=auth_header(operator))

  body = response.get_json()
  assert body['status'] == 'ok'
  assert len(body['entries']) == 3
  assert [(entry['day_of_week'], entry['start_time']) for entry in body['entries']] == [
    (0, '08:00:00'),
    (0, '14:00:00'),
    (2, '09:00:00'),
  ]


def test_multiple_entries_same_day_allowed(client):
  admin = create_user(UserRole.ADMIN)
  transport = create_transport()
  _entry(transport, day_of_week=0, start='08:00:00', end='12:00:00')

  response = client.post(
    '/delivery-coverage',
    json={
      'day_of_week': 0,
      'transport_id': transport.id,
      'start_time': '13:00',
      'end_time': '18:00',
      'caps': ['70053'],
    },
    headers=auth_header(admin),
  )

  assert response.get_json()['status'] == 'ok'


def test_update_entry(client):
  admin = create_user(UserRole.ADMIN)
  other_transport = create_transport()
  entry = _entry(create_transport(), day_of_week=0, start='08:00:00', end='17:00:00', caps=('70051',))

  response = client.put(
    f'/delivery-coverage/{entry.id}',
    json={
      'day_of_week': 3,
      'transport_id': other_transport.id,
      'start_time': '07:30',
      'end_time': '16:00',
      'caps': ['70099'],
    },
    headers=auth_header(admin),
  )

  body = response.get_json()
  assert body['status'] == 'ok'
  assert body['entry']['day_of_week'] == 3
  assert body['entry']['transport_id'] == other_transport.id
  assert body['entry']['start_time'] == '07:30:00'
  assert body['entry']['caps'] == ['70099']
  updated = get_by_id(DeliveryCoverageEntry, entry.id)
  assert updated.day_of_week == 3


def test_update_entry_not_found(client):
  admin = create_user(UserRole.ADMIN)

  response = client.put('/delivery-coverage/999', json={'start_time': '09:00'}, headers=auth_header(admin))

  assert response.get_json() == {'status': 'ko', 'message': 'Blocco non trovato'}


def test_update_entry_rejects_missing_transport(client):
  admin = create_user(UserRole.ADMIN)
  entry = _entry(create_transport())

  response = client.put(
    f'/delivery-coverage/{entry.id}',
    json={'transport_id': 999},
    headers=auth_header(admin),
  )

  assert response.get_json() == {'status': 'ko', 'message': 'Veicolo non trovato'}


def test_update_entry_rejects_reversed_times(client):
  admin = create_user(UserRole.ADMIN)
  entry = _entry(create_transport(), start='08:00:00', end='17:00:00')

  response = client.put(
    f'/delivery-coverage/{entry.id}',
    json={'start_time': '18:00'},
    headers=auth_header(admin),
  )

  assert response.get_json()['status'] == 'ko'


def test_update_entry_rejects_empty_caps(client):
  admin = create_user(UserRole.ADMIN)
  entry = _entry(create_transport())

  response = client.put(
    f'/delivery-coverage/{entry.id}',
    json={'caps': []},
    headers=auth_header(admin),
  )

  assert response.get_json() == {'status': 'ko', 'message': 'Seleziona almeno un CAP'}


def test_delete_entry_cascades_caps(client):
  admin = create_user(UserRole.ADMIN)
  entry = _entry(create_transport(), caps=('70051', '70052'))
  cap_ids = [cap.id for cap in get_by_params(DeliveryCoverageCap, [('entry_id', entry.id)])]
  assert len(cap_ids) == 2

  response = client.delete(f'/delivery-coverage/{entry.id}', headers=auth_header(admin))

  assert response.get_json()['status'] == 'ok'
  assert get_by_id(DeliveryCoverageEntry, entry.id) is None
  for cap_id in cap_ids:
    assert get_by_id(DeliveryCoverageCap, cap_id) is None


def test_delete_entry_not_found(client):
  admin = create_user(UserRole.ADMIN)

  response = client.delete('/delivery-coverage/999', headers=auth_header(admin))

  assert response.get_json() == {'status': 'ko', 'message': 'Blocco non trovato'}


def test_coverage_endpoints_forbid_delivery_role(client):
  delivery = create_user(UserRole.DELIVERY)

  response = client.get('/delivery-coverage', headers=auth_header(delivery))

  assert response.status_code == 403
  assert response.get_json()['status'] == 'forbidden'

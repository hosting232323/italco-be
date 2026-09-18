from datetime import date, time, timedelta
from unittest.mock import patch

from database_api.operations import create, get_by_id, get_by_params

from src.database.enum import UserRole
from src.database.schema import DeliveryCoverageCap, DeliveryCoverageEntry
from src.end_points.delivery_coverage import (
  available_slots,
  available_slots_by_date,
  check_delivery_coverage,
  check_delivery_coverage_slots,
  resolve_delivery_slot,
)

from tests.unit.factories import (
  auth_header,
  create_order,
  create_product_row,
  create_service,
  create_service_user,
  create_transport,
  create_user,
  customer_with_service,
)


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

  assert response.get_json() == {'status': 'ko', 'message': 'Seleziona almeno un CAP o disegna una zona sulla mappa'}


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


def test_create_entry_rejects_overlap_same_vehicle(client):
  admin = create_user(UserRole.ADMIN)
  transport = create_transport()
  _entry(transport, day_of_week=0, start='08:00:00', end='12:00:00')

  response = client.post(
    '/delivery-coverage',
    json={
      'day_of_week': 0,
      'transport_id': transport.id,
      'start_time': '11:00',
      'end_time': '14:00',
      'caps': ['70053'],
    },
    headers=auth_header(admin),
  )

  assert response.get_json() == {'status': 'ko', 'message': 'Il veicolo ha già una fascia sovrapposta in quel giorno'}


def test_create_entry_allows_back_to_back_same_vehicle(client):
  admin = create_user(UserRole.ADMIN)
  transport = create_transport()
  _entry(transport, day_of_week=0, start='08:00:00', end='12:00:00')

  response = client.post(
    '/delivery-coverage',
    json={
      'day_of_week': 0,
      'transport_id': transport.id,
      'start_time': '12:00',
      'end_time': '16:00',
      'caps': ['70053'],
    },
    headers=auth_header(admin),
  )

  assert response.get_json()['status'] == 'ok'


def test_create_entry_allows_overlap_different_vehicle(client):
  admin = create_user(UserRole.ADMIN)
  _entry(create_transport(), day_of_week=0, start='08:00:00', end='12:00:00')

  response = client.post(
    '/delivery-coverage',
    json={
      'day_of_week': 0,
      'transport_id': create_transport().id,
      'start_time': '08:00',
      'end_time': '12:00',
      'caps': ['70053'],
    },
    headers=auth_header(admin),
  )

  assert response.get_json()['status'] == 'ok'


def test_create_entry_allows_overlap_same_vehicle_different_day(client):
  admin = create_user(UserRole.ADMIN)
  transport = create_transport()
  _entry(transport, day_of_week=0, start='08:00:00', end='12:00:00')

  response = client.post(
    '/delivery-coverage',
    json={
      'day_of_week': 1,
      'transport_id': transport.id,
      'start_time': '08:00',
      'end_time': '12:00',
      'caps': ['70053'],
    },
    headers=auth_header(admin),
  )

  assert response.get_json()['status'] == 'ok'


def test_update_entry_rejects_overlap_same_vehicle(client):
  admin = create_user(UserRole.ADMIN)
  transport = create_transport()
  _entry(transport, day_of_week=0, start='08:00:00', end='12:00:00')
  entry = _entry(transport, day_of_week=0, start='13:00:00', end='16:00:00')

  response = client.put(
    f'/delivery-coverage/{entry.id}',
    json={'start_time': '11:00'},
    headers=auth_header(admin),
  )

  assert response.get_json() == {'status': 'ko', 'message': 'Il veicolo ha già una fascia sovrapposta in quel giorno'}


def test_update_entry_allows_overlap_with_itself(client):
  admin = create_user(UserRole.ADMIN)
  entry = _entry(create_transport(), day_of_week=0, start='08:00:00', end='12:00:00')

  response = client.put(
    f'/delivery-coverage/{entry.id}',
    json={'start_time': '09:00'},
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

  assert response.get_json() == {'status': 'ko', 'message': 'Seleziona almeno un CAP o disegna una zona sulla mappa'}


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


def test_check_delivery_coverage_without_entries_returns_no_dates(app, db):
  with app.test_request_context(json={'cap': '70051'}):
    allowed = check_delivery_coverage()

  assert allowed == []


def test_check_delivery_coverage_allows_covered_weekday(app, db):
  target = date.today() + timedelta(days=3)
  _entry(create_transport(), day_of_week=target.weekday(), caps=('70051',))

  with app.test_request_context(json={'cap': '70051'}):
    allowed = check_delivery_coverage()

  assert target.strftime('%Y-%m-%d') in allowed
  # Solo i giorni coperti sono ammessi
  assert all(date.fromisoformat(day).weekday() == target.weekday() for day in allowed)


def test_check_delivery_coverage_ignores_entries_for_other_caps(app, db):
  target = date.today() + timedelta(days=3)
  _entry(create_transport(), day_of_week=target.weekday(), caps=('70099',))

  with app.test_request_context(json={'cap': '70051'}):
    allowed = check_delivery_coverage()

  assert allowed == []


def test_check_delivery_coverage_has_no_order_count_limit(app, db):
  # A differenza del vecchio vincolo geografico (Constraint.max_orders), la
  # copertura non satura: tanti ordini quanti arrivano nello stesso giorno
  # per lo stesso CAP restano ammessi.
  target = date.today() + timedelta(days=3)
  _entry(create_transport(), day_of_week=target.weekday(), caps=('70051',))
  create_order(cap='70051', dpc=target)
  create_order(cap='70051', dpc=target)

  with app.test_request_context(json={'cap': '70051'}):
    allowed = check_delivery_coverage()

  assert target.strftime('%Y-%m-%d') in allowed


def test_available_slots_lists_distinct_slots_sorted(db):
  target = date.today() + timedelta(days=3)
  transport = create_transport()
  _entry(transport, day_of_week=target.weekday(), start='13:00:00', end='18:00:00', caps=('70051',))
  _entry(transport, day_of_week=target.weekday(), start='08:00:00', end='12:00:00', caps=('70051',))

  assert available_slots('70051', target) == [
    {'start': '08:00', 'end': '12:00', 'caps': ['70051']},
    {'start': '13:00', 'end': '18:00', 'caps': ['70051']},
  ]


def test_available_slots_does_not_dedupe_same_slot_from_different_vehicles(db):
  # Deciso 2026-09-17: niente scelta automatica nascosta lato lista, il FE mostra tutte
  # le fasce sovrapposte (una per blocco di copertura) così l'operatore/cliente vede che
  # sono due opzioni distinte, anche quando orario e CAP coincidono.
  target = date.today() + timedelta(days=3)
  _entry(create_transport(), day_of_week=target.weekday(), start='08:00:00', end='12:00:00', caps=('70051',))
  _entry(create_transport(), day_of_week=target.weekday(), start='08:00:00', end='12:00:00', caps=('70051',))

  assert available_slots('70051', target) == [
    {'start': '08:00', 'end': '12:00', 'caps': ['70051']},
    {'start': '08:00', 'end': '12:00', 'caps': ['70051']},
  ]


def test_available_slots_distinguishes_overlapping_entries_by_caps(db):
  target = date.today() + timedelta(days=3)
  _entry(create_transport(), day_of_week=target.weekday(), start='08:00:00', end='12:00:00', caps=('70051', '70056'))
  _entry(create_transport(), day_of_week=target.weekday(), start='08:00:00', end='12:00:00', caps=('70051', '76011'))

  assert available_slots('70051', target) == [
    {'start': '08:00', 'end': '12:00', 'caps': ['70051', '70056']},
    {'start': '08:00', 'end': '12:00', 'caps': ['70051', '76011']},
  ]


def test_available_slots_empty_without_coverage(db):
  assert available_slots('70051', date.today()) == []
  assert available_slots(None, date.today()) == []
  assert available_slots('70051', None) == []


def test_available_slots_by_date_only_lists_covered_dates(db):
  target = date.today() + timedelta(days=3)
  _entry(create_transport(), day_of_week=target.weekday(), start='08:00:00', end='12:00:00', caps=('70051',))

  result = available_slots_by_date('70051')

  assert result[target.strftime('%Y-%m-%d')] == [{'start': '08:00', 'end': '12:00', 'caps': ['70051']}]
  assert all(date.fromisoformat(day).weekday() == target.weekday() for day in result)


def test_check_delivery_coverage_slots_matches_check_delivery_coverage_dates(app, db):
  target = date.today() + timedelta(days=3)
  _entry(create_transport(), day_of_week=target.weekday(), start='08:00:00', end='12:00:00', caps=('70051',))

  with app.test_request_context(json={'cap': '70051'}):
    dates = check_delivery_coverage()
    slots = check_delivery_coverage_slots()

  assert sorted(slots.keys()) == sorted(dates)
  assert slots[target.strftime('%Y-%m-%d')] == [{'start': '08:00', 'end': '12:00', 'caps': ['70051']}]


def test_resolve_delivery_slot_returns_none_without_coverage(db):
  assert resolve_delivery_slot('70051', date.today()) == (None, None)


def test_resolve_delivery_slot_returns_none_for_missing_cap_or_date(db):
  assert resolve_delivery_slot(None, date.today()) == (None, None)
  assert resolve_delivery_slot('70051', None) == (None, None)


def test_resolve_delivery_slot_returns_none_for_unparsable_string_date(db):
  assert resolve_delivery_slot('70051', 'non-una-data') == (None, None)


def test_resolve_delivery_slot_single_entry(db):
  target = date.today() + timedelta(days=3)
  entry = _entry(create_transport(), day_of_week=target.weekday(), start='08:00:00', end='12:00:00', caps=('70051',))

  assert resolve_delivery_slot('70051', target) == (entry.start_time, entry.end_time)


def test_resolve_delivery_slot_accepts_iso_string_date(db):
  target = date.today() + timedelta(days=3)
  entry = _entry(create_transport(), day_of_week=target.weekday(), start='08:00:00', end='12:00:00', caps=('70051',))

  assert resolve_delivery_slot('70051', target.strftime('%Y-%m-%d')) == (entry.start_time, entry.end_time)


def test_resolve_delivery_slot_picks_least_loaded_slot(db):
  target = date.today() + timedelta(days=3)
  busy = _entry(create_transport(), day_of_week=target.weekday(), start='08:00:00', end='12:00:00', caps=('70051',))
  quiet = _entry(create_transport(), day_of_week=target.weekday(), start='13:00:00', end='18:00:00', caps=('70051',))
  create_order(cap='70051', dpc=target, delivery_slot_start=busy.start_time, delivery_slot_end=busy.end_time)

  assert resolve_delivery_slot('70051', target) == (quiet.start_time, quiet.end_time)


def test_resolve_delivery_slot_uses_requested_slot_when_it_matches_coverage(db):
  target = date.today() + timedelta(days=3)
  busy = _entry(create_transport(), day_of_week=target.weekday(), start='08:00:00', end='12:00:00', caps=('70051',))
  # La fascia più scarica (13-18) esiste ma il cliente ha scelto busy sul
  # calendario: senza scelta esplicita vincerebbe l'altra (meno carico).
  _entry(create_transport(), day_of_week=target.weekday(), start='13:00:00', end='18:00:00', caps=('70051',))
  create_order(cap='70051', dpc=target, delivery_slot_start=busy.start_time, delivery_slot_end=busy.end_time)

  result = resolve_delivery_slot('70051', target, requested_start=busy.start_time, requested_end=busy.end_time)

  assert result == (busy.start_time, busy.end_time)


def test_resolve_delivery_slot_accepts_requested_slot_as_string(db):
  target = date.today() + timedelta(days=3)
  entry = _entry(create_transport(), day_of_week=target.weekday(), start='08:00:00', end='12:00:00', caps=('70051',))

  result = resolve_delivery_slot('70051', target, requested_start='08:00', requested_end='12:00')

  assert result == (entry.start_time, entry.end_time)


def test_resolve_delivery_slot_falls_back_when_requested_slot_not_covered(db):
  target = date.today() + timedelta(days=3)
  entry = _entry(create_transport(), day_of_week=target.weekday(), start='08:00:00', end='12:00:00', caps=('70051',))

  result = resolve_delivery_slot('70051', target, requested_start='20:00', requested_end='22:00')

  assert result == (entry.start_time, entry.end_time)


def test_resolve_delivery_slot_excludes_given_order_from_count(db):
  # Con lo slot del proprio ordine escluso dal conteggio, busy torna in
  # parità con quiet (0 a 0): a parità vince lo start_time più basso.
  target = date.today() + timedelta(days=3)
  busy = _entry(create_transport(), day_of_week=target.weekday(), start='08:00:00', end='12:00:00', caps=('70051',))
  _entry(create_transport(), day_of_week=target.weekday(), start='13:00:00', end='18:00:00', caps=('70051',))
  own_order = create_order(
    cap='70051', dpc=target, delivery_slot_start=busy.start_time, delivery_slot_end=busy.end_time
  )

  result = resolve_delivery_slot('70051', target, exclude_order_id=own_order.id)

  assert result == (busy.start_time, busy.end_time)


def test_available_slots_filters_saturated_slot_based_on_service_duration(db):
  target = date.today() + timedelta(days=3)
  customer, service, service_user, _ = customer_with_service(duration=40)
  # Fascia da 1 ora (60 minuti)
  entry = _entry(create_transport(), day_of_week=target.weekday(), start='08:00:00', end='09:00:00', caps=('70051',))

  # Ordine esistente di 40 minuti nella fascia
  existing_order = create_order(
    cap='70051', dpc=target, delivery_slot_start=entry.start_time, delivery_slot_end=entry.end_time
  )
  create_product_row(existing_order, service_user)

  # Richiesta con 30 minuti di servizio -> 40 + 30 = 70 > 60: slot saturo
  assert available_slots('70051', target, required_duration=30) == []

  # Richiesta con 15 minuti di servizio -> 40 + 15 = 55 <= 60: slot disponibile
  assert available_slots('70051', target, required_duration=15) == [
    {'start': '08:00', 'end': '09:00', 'caps': ['70051']}
  ]


def test_available_slots_sums_multiple_products_durations(db):
  target = date.today() + timedelta(days=3)
  customer = create_user(UserRole.CUSTOMER)
  service1 = create_service(duration=20)
  service2 = create_service(duration=30)
  su1 = create_service_user(customer, service1)
  su2 = create_service_user(customer, service2)

  # Fascia da 60 minuti
  entry = _entry(create_transport(), day_of_week=target.weekday(), start='08:00:00', end='09:00:00', caps=('70051',))
  existing_order = create_order(
    cap='70051', dpc=target, delivery_slot_start=entry.start_time, delivery_slot_end=entry.end_time
  )
  # Ordine ha 2 prodotti: 20 + 30 = 50 min occupati
  create_product_row(existing_order, su1, name='P1')
  create_product_row(existing_order, su2, name='P2')

  # Con 50 min occupati su 60 min, una richiesta da 20 min sfora (50 + 20 = 70 > 60)
  assert available_slots('70051', target, required_duration=20) == []
  # Una richiesta da 10 min ci sta (50 + 10 = 60 <= 60)
  assert available_slots('70051', target, required_duration=10) == [
    {'start': '08:00', 'end': '09:00', 'caps': ['70051']}
  ]


def test_resolve_delivery_slot_prefers_unsaturated_slot_and_balances_minutes(db):
  target = date.today() + timedelta(days=3)
  customer, service, service_user, _ = customer_with_service(duration=60)
  # Due fasce: Mattina (08-10 = 120 min) e Pomeriggio (14-16 = 120 min)
  morning = _entry(create_transport(), day_of_week=target.weekday(), start='08:00:00', end='10:00:00', caps=('70051',))
  afternoon = _entry(
    create_transport(), day_of_week=target.weekday(), start='14:00:00', end='16:00:00', caps=('70051',)
  )

  # Mattina ha già un ordine da 60 min (rimangono 60 min)
  order_morning = create_order(
    cap='70051', dpc=target, delivery_slot_start=morning.start_time, delivery_slot_end=morning.end_time
  )
  create_product_row(order_morning, service_user)

  # Nuovo ordine da 90 min: Mattina non ha spazio (60 + 90 = 150 > 120), Pomeriggio sì (0 + 90 = 90 <= 120)
  chosen_start, chosen_end = resolve_delivery_slot('70051', target, required_duration=90)
  assert (chosen_start, chosen_end) == (afternoon.start_time, afternoon.end_time)


@patch('src.end_points.service.travel.sequential_travel_minutes')
@patch('src.end_points.service.travel.get_lat_lon_by_address')
@patch('src.end_points.service.travel.get_lat_lon_by_cap')
def test_available_slots_filters_saturated_slot_based_on_travel_overhead(
  mock_geocode, mock_geocode_address, mock_sequential, db
):
  target = date.today() + timedelta(days=3)
  # Fascia da 1 ora (60 minuti), nessuna durata di servizio: satura solo per via del percorso.
  entry = _entry(create_transport(), day_of_week=target.weekday(), start='08:00:00', end='09:00:00', caps=('70051',))
  create_order(cap='70051', dpc=target, delivery_slot_start=entry.start_time, delivery_slot_end=entry.end_time)

  # L'indirizzo dell'ordine esistente non deve risolvere: il test guida le
  # coordinate via CAP.
  mock_geocode_address.return_value = (None, None)
  mock_geocode.return_value = (41.0, 16.0)
  # baseline (solo l'esistente): 20 min. Con il nuovo ordine aggiunto: 90 min -> overhead 70 min.
  mock_sequential.side_effect = lambda coords: 20 if len(coords) == 1 else 90

  assert available_slots('70051', target, new_cap='70051') == []


@patch('src.end_points.service.travel.get_lat_lon_by_cap')
def test_available_slots_ignores_travel_overhead_when_new_cap_unresolvable(mock_geocode, db):
  target = date.today() + timedelta(days=3)
  entry = _entry(create_transport(), day_of_week=target.weekday(), start='08:00:00', end='09:00:00', caps=('70051',))
  create_order(cap='70051', dpc=target, delivery_slot_start=entry.start_time, delivery_slot_end=entry.end_time)

  mock_geocode.return_value = (None, None)

  assert available_slots('70051', target, new_cap='70051') == [{'start': '08:00', 'end': '09:00', 'caps': ['70051']}]


def test_available_slots_without_new_cap_skips_travel_overhead(db):
  target = date.today() + timedelta(days=3)
  entry = _entry(create_transport(), day_of_week=target.weekday(), start='08:00:00', end='09:00:00', caps=('70051',))
  create_order(cap='70051', dpc=target, delivery_slot_start=entry.start_time, delivery_slot_end=entry.end_time)

  assert available_slots('70051', target) == [{'start': '08:00', 'end': '09:00', 'caps': ['70051']}]


def test_available_slots_keeps_saturated_entry_when_same_vehicle_adjacent_slot_is_free(db):
  # 09:00-11:30 satura (stesso veicolo), 12:00-14:30 dello stesso veicolo libera ma per
  # un CAP diverso: la fascia satura resta comunque disponibile perché il veicolo passa
  # comunque nella fascia successiva e può assorbire l'ordine lì.
  target = date.today() + timedelta(days=3)
  transport = create_transport()
  customer, service, service_user, _ = customer_with_service(duration=150)
  morning = _entry(transport, day_of_week=target.weekday(), start='09:00:00', end='11:30:00', caps=('70051',))
  _entry(transport, day_of_week=target.weekday(), start='12:00:00', end='14:30:00', caps=('70052',))

  existing_order = create_order(
    cap='70051', dpc=target, delivery_slot_start=morning.start_time, delivery_slot_end=morning.end_time
  )
  create_product_row(existing_order, service_user)

  assert available_slots('70051', target, required_duration=30) == [
    {'start': '09:00', 'end': '11:30', 'caps': ['70051']}
  ]


def test_available_slots_drops_saturated_entry_when_no_adjacent_vehicle_slot_is_free(db):
  # Come sopra ma la fascia successiva dello stesso veicolo è satura anche lei: nessuno
  # spillover possibile, la fascia satura sparisce dalla lista.
  target = date.today() + timedelta(days=3)
  transport = create_transport()
  customer, service, service_user, _ = customer_with_service(duration=150)
  morning = _entry(transport, day_of_week=target.weekday(), start='09:00:00', end='11:30:00', caps=('70051',))
  afternoon = _entry(transport, day_of_week=target.weekday(), start='12:00:00', end='14:30:00', caps=('70052',))

  existing_morning = create_order(
    cap='70051', dpc=target, delivery_slot_start=morning.start_time, delivery_slot_end=morning.end_time
  )
  create_product_row(existing_morning, service_user)
  existing_afternoon = create_order(
    cap='70052', dpc=target, delivery_slot_start=afternoon.start_time, delivery_slot_end=afternoon.end_time
  )
  create_product_row(existing_afternoon, service_user)

  assert available_slots('70051', target, required_duration=30) == []


def test_available_slots_ignores_full_slot_of_a_different_vehicle(db):
  # La fascia adiacente libera appartiene a un veicolo diverso: non conta come spillover
  # ("sempre fasce relative allo stesso corriere").
  target = date.today() + timedelta(days=3)
  customer, service, service_user, _ = customer_with_service(duration=150)
  morning = _entry(create_transport(), day_of_week=target.weekday(), start='09:00:00', end='11:30:00', caps=('70051',))
  _entry(create_transport(), day_of_week=target.weekday(), start='12:00:00', end='14:30:00', caps=('70051',))

  existing_order = create_order(
    cap='70051', dpc=target, delivery_slot_start=morning.start_time, delivery_slot_end=morning.end_time
  )
  create_product_row(existing_order, service_user)

  # La fascia satura sparisce (nessuno spillover cross-veicolo); resta comunque visibile
  # la fascia 12:00-14:30 perché copre 70051 per conto proprio, indipendentemente dallo
  # spillover.
  assert available_slots('70051', target, required_duration=30) == [
    {'start': '12:00', 'end': '14:30', 'caps': ['70051']}
  ]


def test_resolve_delivery_slot_spills_over_to_adjacent_slot_of_same_vehicle(db):
  target = date.today() + timedelta(days=3)
  transport = create_transport()
  customer, service, service_user, _ = customer_with_service(duration=150)
  morning = _entry(transport, day_of_week=target.weekday(), start='09:00:00', end='11:30:00', caps=('70051',))
  afternoon = _entry(transport, day_of_week=target.weekday(), start='12:00:00', end='14:30:00', caps=('70052',))

  existing_order = create_order(
    cap='70051', dpc=target, delivery_slot_start=morning.start_time, delivery_slot_end=morning.end_time
  )
  create_product_row(existing_order, service_user)

  result = resolve_delivery_slot(
    '70051', target, requested_start=morning.start_time, requested_end=morning.end_time, required_duration=30
  )

  assert result == (afternoon.start_time, afternoon.end_time)


def test_resolve_delivery_slot_honors_requested_slot_when_no_spillover_available(db):
  # Fascia satura, nessuna adiacente sullo stesso veicolo libera: comportamento
  # preesistente, si onora comunque la scelta esplicita del cliente.
  target = date.today() + timedelta(days=3)
  transport = create_transport()
  customer, service, service_user, _ = customer_with_service(duration=150)
  morning = _entry(transport, day_of_week=target.weekday(), start='09:00:00', end='11:30:00', caps=('70051',))

  existing_order = create_order(
    cap='70051', dpc=target, delivery_slot_start=morning.start_time, delivery_slot_end=morning.end_time
  )
  create_product_row(existing_order, service_user)

  result = resolve_delivery_slot(
    '70051', target, requested_start=morning.start_time, requested_end=morning.end_time, required_duration=30
  )

  assert result == (morning.start_time, morning.end_time)

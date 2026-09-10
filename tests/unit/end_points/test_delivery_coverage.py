from datetime import date, time, timedelta

from database_api.operations import create, get_by_id

from src.database.enum import UserRole
from src.database.schema import DeliveryAbsence, DeliveryCoverage, DeliveryCoverageDay

from tests.unit.factories import auth_header, create_user


def _coverage(user, start=None, end=None):
  start = start or date.today()
  end = end or (start + timedelta(days=30))
  return create(DeliveryCoverage, {'user_id': user.id, 'start_date': start, 'end_date': end})


def _day(coverage, day_of_week=0, start='08:00:00', end='17:00:00'):
  return create(
    DeliveryCoverageDay,
    {
      'coverage_id': coverage.id,
      'day_of_week': day_of_week,
      'start_time': time.fromisoformat(start),
      'end_time': time.fromisoformat(end),
    },
  )


def test_create_coverage(client):
  admin = create_user(UserRole.ADMIN)
  delivery = create_user(UserRole.DELIVERY)

  response = client.post(
    '/delivery-coverage',
    json={'user_id': delivery.id, 'start_date': '2026-09-01', 'end_date': '2026-12-31'},
    headers=auth_header(admin),
  )

  body = response.get_json()
  assert body['status'] == 'ok'
  assert body['coverage']['days'] == []
  assert get_by_id(DeliveryCoverage, body['coverage']['id']) is not None


def test_create_coverage_rejects_non_delivery_user(client):
  admin = create_user(UserRole.ADMIN)
  customer = create_user(UserRole.CUSTOMER)

  response = client.post(
    '/delivery-coverage',
    json={'user_id': customer.id, 'start_date': '2026-09-01', 'end_date': '2026-12-31'},
    headers=auth_header(admin),
  )

  assert response.get_json() == {'status': 'ko', 'message': 'Utente delivery non trovato'}


def test_create_coverage_rejects_end_before_start(client):
  admin = create_user(UserRole.ADMIN)
  delivery = create_user(UserRole.DELIVERY)

  response = client.post(
    '/delivery-coverage',
    json={'user_id': delivery.id, 'start_date': '2026-12-31', 'end_date': '2026-09-01'},
    headers=auth_header(admin),
  )

  assert response.get_json()['status'] == 'ko'


def test_get_delivery_coverage_aggregates(client):
  operator = create_user(UserRole.OPERATOR)
  delivery = create_user(UserRole.DELIVERY)
  coverage = _coverage(delivery)
  _day(coverage, day_of_week=0)
  _day(coverage, day_of_week=2)
  create(DeliveryAbsence, {'user_id': delivery.id, 'start_date': date.today(), 'end_date': date.today()})

  response = client.get('/delivery-coverage', headers=auth_header(operator))

  body = response.get_json()
  assert body['status'] == 'ok'
  assert [user['id'] for user in body['delivery_users']] == [delivery.id]
  assert len(body['coverages']) == 1
  assert len(body['coverages'][0]['days']) == 2
  assert len(body['absences']) == 1


def test_add_coverage_day(client):
  admin = create_user(UserRole.ADMIN)
  coverage = _coverage(create_user(UserRole.DELIVERY))

  response = client.post(
    f'/delivery-coverage/{coverage.id}/day',
    json={'day_of_week': 3, 'start_time': '09:00', 'end_time': '13:30'},
    headers=auth_header(admin),
  )

  body = response.get_json()
  assert body['status'] == 'ok'
  assert body['day']['start_time'] == '09:00:00'


def test_add_coverage_day_rejects_invalid_day(client):
  admin = create_user(UserRole.ADMIN)
  coverage = _coverage(create_user(UserRole.DELIVERY))

  response = client.post(
    f'/delivery-coverage/{coverage.id}/day',
    json={'day_of_week': 9, 'start_time': '09:00', 'end_time': '13:30'},
    headers=auth_header(admin),
  )

  assert response.get_json() == {'status': 'ko', 'message': 'Errore generico'}


def test_add_coverage_day_rejects_duplicate(client):
  admin = create_user(UserRole.ADMIN)
  coverage = _coverage(create_user(UserRole.DELIVERY))
  _day(coverage, day_of_week=1)

  response = client.post(
    f'/delivery-coverage/{coverage.id}/day',
    json={'day_of_week': 1, 'start_time': '09:00', 'end_time': '13:30'},
    headers=auth_header(admin),
  )

  assert response.get_json()['status'] == 'ko'


def test_add_coverage_day_rejects_reversed_times(client):
  admin = create_user(UserRole.ADMIN)
  coverage = _coverage(create_user(UserRole.DELIVERY))

  response = client.post(
    f'/delivery-coverage/{coverage.id}/day',
    json={'day_of_week': 1, 'start_time': '15:00', 'end_time': '09:00'},
    headers=auth_header(admin),
  )

  assert response.get_json()['status'] == 'ko'


def test_delete_coverage_cascades_days(client):
  admin = create_user(UserRole.ADMIN)
  coverage = _coverage(create_user(UserRole.DELIVERY))
  day = _day(coverage)

  response = client.delete(f'/delivery-coverage/{coverage.id}', headers=auth_header(admin))

  assert response.get_json()['status'] == 'ok'
  assert get_by_id(DeliveryCoverage, coverage.id) is None
  assert get_by_id(DeliveryCoverageDay, day.id) is None


def test_update_coverage_dates(client):
  admin = create_user(UserRole.ADMIN)
  coverage = _coverage(create_user(UserRole.DELIVERY))

  response = client.put(
    f'/delivery-coverage/{coverage.id}',
    json={'end_date': '2027-01-31'},
    headers=auth_header(admin),
  )

  assert response.get_json()['status'] == 'ok'
  assert get_by_id(DeliveryCoverage, coverage.id).end_date == date(2027, 1, 31)


def test_absence_crud(client):
  admin = create_user(UserRole.ADMIN)
  delivery = create_user(UserRole.DELIVERY)

  created = client.post(
    '/delivery-coverage/absence',
    json={'user_id': delivery.id, 'start_date': '2026-09-10', 'end_date': '2026-09-14', 'note': 'Ferie'},
    headers=auth_header(admin),
  ).get_json()
  assert created['status'] == 'ok'
  absence_id = created['absence']['id']

  updated = client.put(
    f'/delivery-coverage/absence/{absence_id}',
    json={'note': 'Permesso'},
    headers=auth_header(admin),
  ).get_json()
  assert updated['absence']['note'] == 'Permesso'

  deleted = client.delete(f'/delivery-coverage/absence/{absence_id}', headers=auth_header(admin))
  assert deleted.get_json()['status'] == 'ok'
  assert get_by_id(DeliveryAbsence, absence_id) is None


def test_coverage_endpoints_forbid_delivery_role(client):
  delivery = create_user(UserRole.DELIVERY)

  response = client.get('/delivery-coverage', headers=auth_header(delivery))

  assert response.status_code == 403
  assert response.get_json()['status'] == 'forbidden'

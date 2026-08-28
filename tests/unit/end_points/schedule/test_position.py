from datetime import date

from src.database.enum import ScheduleItemUserType, UserRole
from src.end_points.schedule.position import claim_schedule_position, get_schedule_position

from tests.unit.factories import (
  auth_header,
  create_delivery_group,
  create_schedule,
  create_schedule_item_user,
  create_user,
)


def _bordero_with_couriers():
  first = create_user(UserRole.DELIVERY)
  second = create_user(UserRole.DELIVERY)
  schedule = create_schedule(schedule_date=date.today())
  create_delivery_group(first, schedule)
  create_delivery_group(second, schedule)
  return first, second, schedule


def test_get_schedule_position_is_none_before_activation(db):
  delivery, _, schedule = _bordero_with_couriers()

  result = get_schedule_position(delivery, schedule.id)

  assert result == {'status': 'ok', 'holder': None}


def test_claim_schedule_position_opens_when_free(db):
  delivery, _, schedule = _bordero_with_couriers()

  result = claim_schedule_position(delivery, schedule.id)

  assert result['status'] == 'ok'
  assert result['holder']['id'] == delivery.id
  assert result['holder']['type'] == ScheduleItemUserType.OPENING.value


def test_claim_schedule_position_is_idempotent_for_current_holder(db):
  delivery, _, schedule = _bordero_with_couriers()
  claim_schedule_position(delivery, schedule.id)

  result = claim_schedule_position(delivery, schedule.id)

  assert result['holder']['type'] == ScheduleItemUserType.OPENING.value
  assert get_schedule_position(delivery, schedule.id)['holder']['id'] == delivery.id


def test_colleague_can_take_control_with_change_event(db):
  first, second, schedule = _bordero_with_couriers()
  claim_schedule_position(first, schedule.id)

  result = claim_schedule_position(second, schedule.id)

  assert result['status'] == 'ok'
  assert result['holder']['id'] == second.id
  assert result['holder']['type'] == ScheduleItemUserType.CHANGE.value

  status = get_schedule_position(first, schedule.id)
  assert status['holder']['id'] == second.id


def test_claim_schedule_position_reopens_after_closing(db):
  first, second, schedule = _bordero_with_couriers()
  claim_schedule_position(first, schedule.id)
  create_schedule_item_user(first, schedule, ScheduleItemUserType.CLOSING)

  assert get_schedule_position(second, schedule.id) == {'status': 'ok', 'holder': None}

  result = claim_schedule_position(second, schedule.id)

  assert result['holder']['type'] == ScheduleItemUserType.OPENING.value


def test_position_rejects_user_outside_the_bordero(db):
  _, _, schedule = _bordero_with_couriers()
  outsider = create_user(UserRole.DELIVERY)

  assert get_schedule_position(outsider, schedule.id)['status'] == 'ko'
  assert claim_schedule_position(outsider, schedule.id)['status'] == 'ko'


def test_position_rejects_unknown_schedule(db):
  delivery = create_user(UserRole.DELIVERY)

  assert get_schedule_position(delivery, 424242)['status'] == 'ko'
  assert claim_schedule_position(delivery, 424242)['status'] == 'ko'


def test_position_endpoints(client):
  first, second, schedule = _bordero_with_couriers()

  get_response = client.get(f'/schedule/{schedule.id}/position', headers=auth_header(first))
  assert get_response.get_json()['status'] == 'ok'
  assert get_response.get_json()['holder'] is None

  claim_response = client.post(f'/schedule/{schedule.id}/position', headers=auth_header(first))
  assert claim_response.get_json()['holder']['id'] == first.id

  take_response = client.post(f'/schedule/{schedule.id}/position', headers=auth_header(second))
  assert take_response.get_json()['holder']['id'] == second.id
  assert take_response.get_json()['holder']['type'] == ScheduleItemUserType.CHANGE.value

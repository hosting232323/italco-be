from datetime import date

from database_api import Session

from src.database.enum import ScheduleItemUserType, UserRole
from src.database.schema import DeliveryUserInfo
from src.end_points.schedule.position import (
  claim_schedule_position,
  get_schedule_position,
  holder_required_error,
)
from src.end_points.schedule.delivery import update_schedule_item

from tests.unit.factories import (
  auth_header,
  assign_delivery_user_to_schedule,
  create_schedule,
  create_schedule_item_user,
  create_user,
)


COORDS = {'lat': 41.2, 'lon': 16.3}


def _bordero_with_couriers():
  first = create_user(UserRole.DELIVERY)
  second = create_user(UserRole.DELIVERY)
  schedule = create_schedule(schedule_date=date.today())
  assign_delivery_user_to_schedule(first, schedule)
  assign_delivery_user_to_schedule(second, schedule)
  return first, second, schedule


def test_get_schedule_position_is_none_before_activation(db):
  delivery, _, schedule = _bordero_with_couriers()

  result = get_schedule_position(delivery, schedule.id)

  assert result == {'status': 'ok', 'holder': None}


def test_claim_schedule_position_opens_when_free(db):
  delivery, _, schedule = _bordero_with_couriers()

  result = claim_schedule_position(delivery, schedule.id, COORDS)

  assert result['status'] == 'ok'
  assert result['holder']['id'] == delivery.id
  assert result['holder']['type'] == ScheduleItemUserType.OPENING.value


def test_claim_schedule_position_is_idempotent_for_current_holder(db):
  delivery, _, schedule = _bordero_with_couriers()
  claim_schedule_position(delivery, schedule.id, COORDS)

  result = claim_schedule_position(delivery, schedule.id, COORDS)

  assert result['holder']['type'] == ScheduleItemUserType.OPENING.value
  assert get_schedule_position(delivery, schedule.id)['holder']['id'] == delivery.id


def test_colleague_can_take_control_with_change_event(db):
  first, second, schedule = _bordero_with_couriers()
  claim_schedule_position(first, schedule.id, COORDS)

  result = claim_schedule_position(second, schedule.id, COORDS)

  assert result['status'] == 'ok'
  assert result['holder']['id'] == second.id
  assert result['holder']['type'] == ScheduleItemUserType.CHANGE.value

  status = get_schedule_position(first, schedule.id)
  assert status['holder']['id'] == second.id


def test_claim_schedule_position_reopens_after_closing(db):
  first, second, schedule = _bordero_with_couriers()
  claim_schedule_position(first, schedule.id, COORDS)
  create_schedule_item_user(first, schedule, ScheduleItemUserType.CLOSING)

  assert get_schedule_position(second, schedule.id) == {'status': 'ok', 'holder': None}

  result = claim_schedule_position(second, schedule.id, COORDS)

  assert result['holder']['type'] == ScheduleItemUserType.OPENING.value


def test_position_rejects_user_outside_the_bordero(db):
  _, _, schedule = _bordero_with_couriers()
  outsider = create_user(UserRole.DELIVERY)

  assert get_schedule_position(outsider, schedule.id)['status'] == 'ko'
  assert claim_schedule_position(outsider, schedule.id, COORDS)['status'] == 'ko'


def test_position_rejects_unknown_schedule(db):
  delivery = create_user(UserRole.DELIVERY)

  assert get_schedule_position(delivery, 424242)['status'] == 'ko'
  assert claim_schedule_position(delivery, 424242)['status'] == 'ko'


def test_position_endpoints(client):
  first, second, schedule = _bordero_with_couriers()

  get_response = client.get(f'/schedule/{schedule.id}/position', headers=auth_header(first))
  assert get_response.get_json()['status'] == 'ok'
  assert get_response.get_json()['holder'] is None

  claim_response = client.post(f'/schedule/{schedule.id}/position', headers=auth_header(first), json=COORDS)
  assert claim_response.get_json()['holder']['id'] == first.id

  take_response = client.post(f'/schedule/{schedule.id}/position', headers=auth_header(second), json=COORDS)
  assert take_response.get_json()['holder']['id'] == second.id
  assert take_response.get_json()['holder']['type'] == ScheduleItemUserType.CHANGE.value


def test_claim_without_coordinates_is_refused_and_does_not_open(db):
  delivery, _, schedule = _bordero_with_couriers()

  for bad in (None, {}, {'lat': 'x', 'lon': 1}, {'lat': 95, 'lon': 10}, {'lat': 10, 'lon': 190}):
    result = claim_schedule_position(delivery, schedule.id, bad)
    assert result['status'] == 'ko'
    assert result['code'] == 'position_required'

  assert get_schedule_position(delivery, schedule.id)['holder'] is None


def test_claim_saves_the_courier_coordinates(db):
  delivery, _, schedule = _bordero_with_couriers()

  claim_schedule_position(delivery, schedule.id, COORDS)

  with Session() as session:
    info = session.query(DeliveryUserInfo).filter(DeliveryUserInfo.user_id == delivery.id).one()
    assert float(info.lat) == COORDS['lat']
    assert float(info.lon) == COORDS['lon']


def test_only_the_holder_can_edit_the_bordero(db):
  first, second, schedule = _bordero_with_couriers()

  assert holder_required_error(first, schedule.id)['code'] == 'position_not_held'

  claim_schedule_position(first, schedule.id, COORDS)

  assert holder_required_error(first, schedule.id) is None
  assert holder_required_error(second, schedule.id)['code'] == 'position_not_held'

  claim_schedule_position(second, schedule.id, COORDS)

  assert holder_required_error(second, schedule.id) is None
  assert holder_required_error(first, schedule.id)['code'] == 'position_not_held'


def test_nobody_can_edit_after_closing(db):
  first, _, schedule = _bordero_with_couriers()
  claim_schedule_position(first, schedule.id, COORDS)
  create_schedule_item_user(first, schedule, ScheduleItemUserType.CLOSING)

  assert holder_required_error(first, schedule.id)['code'] == 'position_not_held'


def test_non_holder_cannot_complete_schedule_item(db):
  from src.database.enum import ScheduleType
  from tests.unit.factories import create_schedule_item

  first, second, schedule = _bordero_with_couriers()
  item = create_schedule_item(schedule, ScheduleType.COLLECTIONPOINT, index=0)
  claim_schedule_position(first, schedule.id, COORDS)

  refused = update_schedule_item(second, item.id, True)

  assert refused['status'] == 'ko'
  assert refused['code'] == 'position_not_held'
  assert update_schedule_item(first, item.id, True)['status'] == 'ok'


def test_update_schedule_item_unknown_item(db):
  delivery, _, _ = _bordero_with_couriers()

  assert update_schedule_item(delivery, 424242, True)['status'] == 'ko'

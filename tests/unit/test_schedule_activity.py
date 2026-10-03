from datetime import date, timedelta

import pytest
from database_api import Session
from database_api.operations import create

import src.end_points.schedule as schedule_endpoints
from src.database.enum import ScheduleItemUserType
from src.database.schema import Order, ScheduleItem, ScheduleItemActivity, ScheduleItemUser, Transport, User
from src.end_points.schedule.delivery import get_history_for_delivery, get_items_for_delivery, update_schedule_item
from src.end_points.schedule.queries import get_latest_schedule_item_user
from tests.unit.factories import admin_header
from tests.unit.test_schedule_update_transactions import _create_schedule_with_order, _payload, schedule_client  # noqa: F401


@pytest.fixture(autouse=True)
def no_side_effects(monkeypatch):
  monkeypatch.setattr(schedule_endpoints, 'save_info_to_euronics', lambda _: None)
  monkeypatch.setattr(schedule_endpoints, 'schedule_sms_check', lambda *_: None)


def _activity(**overrides):
  return {
    'index': 1,
    'operation_type': 'Activity',
    'start_time_slot': '10:00',
    'end_time_slot': '10:30',
    'title': 'Pausa pranzo',
    **overrides,
  }


def _setup():
  with Session() as session:
    delivery = session.query(User).filter_by(nickname='delivery_1').one()
    delivery_id = delivery.id
  schedule_id, item_id, order_id, transport_id = _create_schedule_with_order(delivery)
  payload = _payload(schedule_id, item_id, order_id, transport_id, delivery_id, deleted_users=[])
  return delivery, schedule_id, payload


def _put(client, schedule_id, payload):
  return client.put(f'/schedule/{schedule_id}', json=payload, headers=admin_header()).get_json()


def _activities(schedule_id):
  with Session() as session:
    return (
      session.query(ScheduleItemActivity)
      .join(ScheduleItem, ScheduleItem.id == ScheduleItemActivity.schedule_item_id)
      .filter(ScheduleItem.schedule_id == schedule_id)
      .all()
    )


def test_create_schedule_with_activity(schedule_client):  # noqa: F811
  with Session() as session:
    delivery_id = session.query(User).filter_by(nickname='delivery_1').one().id
    transport_id = session.query(Transport).first().id
    order_id = session.query(Order).first().id

  response = schedule_client.post(
    '/schedule/',
    json={
      'date': (date.today() + timedelta(days=60)).isoformat(),
      'transport_id': transport_id,
      'users': [{'id': delivery_id}],
      'schedule_items': [
        {
          'index': 0,
          'operation_type': 'Order',
          'order_id': order_id,
          'start_time_slot': '08:00',
          'end_time_slot': '10:00',
        },
        _activity(note='  in piazzale  '),
      ],
    },
    headers=admin_header(),
  ).get_json()

  assert response['status'] == 'ok'
  activity = _activities(response['schedule']['id'])[0]
  # La durata non impostata vale 0, le stringhe vuote diventano NULL.
  assert (activity.title, activity.note, activity.duration_minutes) == ('Pausa pranzo', 'in piazzale', 0)
  assert (activity.address, activity.cap) == (None, None)


def test_activity_is_returned_by_schedule_filter(schedule_client):  # noqa: F811
  _, schedule_id, payload = _setup()
  payload['schedule_items'].append(_activity(duration_minutes=45, address='Via Roma 1, Bisceglie', cap='70052'))
  assert _put(schedule_client, schedule_id, payload)['status'] == 'ok'

  body = schedule_client.post(
    '/schedule/filter',
    json={'filters': [{'model': 'Schedule', 'field': 'id', 'value': schedule_id}]},
    headers=admin_header(),
  ).get_json()

  items = body['schedules'][0]['schedule_items']
  activity = next(item for item in items if item['operation_type'] == 'Activity')
  assert activity['title'] == 'Pausa pranzo'
  assert activity['duration_minutes'] == 45
  assert (activity['address'], activity['cap']) == ('Via Roma 1, Bisceglie', '70052')
  assert activity['start_time_slot'] == '10:00:00'
  assert len(items) == 2


def test_activity_is_returned_when_filtering_by_order_id(schedule_client):  # noqa: F811
  _, schedule_id, payload = _setup()
  payload['schedule_items'].append(_activity())
  assert _put(schedule_client, schedule_id, payload)['status'] == 'ok'
  order_id = payload['schedule_items'][0]['order_id']

  body = schedule_client.post(
    '/schedule/filter',
    json={'filters': [{'model': 'Order', 'field': 'id', 'value': order_id}]},
    headers=admin_header(),
  ).get_json()

  items = body['schedules'][0]['schedule_items']
  assert sorted(item['operation_type'] for item in items) == ['Activity', 'Order']


@pytest.mark.parametrize(
  ('overrides', 'message'),
  [
    ({'title': '   '}, 'titolo'),
    ({'duration_minutes': -5}, 'durata'),
    ({'duration_minutes': '20'}, 'durata'),
  ],
)
def test_invalid_activity_is_rejected(schedule_client, overrides, message):  # noqa: F811
  _, schedule_id, payload = _setup()
  payload['schedule_items'].append(_activity(**overrides))

  body = _put(schedule_client, schedule_id, payload)

  assert body['status'] == 'ko'
  assert message in body['message']
  assert _activities(schedule_id) == []


def test_activity_address_without_cap_is_accepted(schedule_client):  # noqa: F811
  _, schedule_id, payload = _setup()
  payload['schedule_items'].append(_activity(address='Via Roma 1, Bisceglie'))

  assert _put(schedule_client, schedule_id, payload)['status'] == 'ok'

  activity = _activities(schedule_id)[0]
  assert (activity.address, activity.cap) == ('Via Roma 1, Bisceglie', None)


def test_update_edits_and_removes_activity(schedule_client):  # noqa: F811
  _, schedule_id, payload = _setup()
  payload['schedule_items'].append(_activity(duration_minutes=30))
  assert _put(schedule_client, schedule_id, payload)['status'] == 'ok'
  activity_item_id = _activities(schedule_id)[0].schedule_item_id

  payload['schedule_items'][1] = _activity(id=activity_item_id, title='Rifornimento', duration_minutes=20)
  assert _put(schedule_client, schedule_id, payload)['status'] == 'ok'
  activities = _activities(schedule_id)
  assert [(a.title, a.duration_minutes) for a in activities] == [('Rifornimento', 20)]

  payload['schedule_items'].pop(1)
  assert _put(schedule_client, schedule_id, payload)['status'] == 'ok'
  assert _activities(schedule_id) == []
  with Session() as session:
    assert session.query(ScheduleItem).filter_by(schedule_id=schedule_id).count() == 1


def test_delete_schedule_removes_activity(schedule_client):  # noqa: F811
  _, schedule_id, payload = _setup()
  payload['schedule_items'].append(_activity())
  assert _put(schedule_client, schedule_id, payload)['status'] == 'ok'

  body = schedule_client.delete(f'/schedule/{schedule_id}', headers=admin_header()).get_json()

  assert body['status'] == 'ok'
  assert _activities(schedule_id) == []


def test_delivery_does_not_receive_activities(schedule_client):  # noqa: F811
  delivery, schedule_id, payload = _setup()
  payload['schedule_items'].append(_activity())
  assert _put(schedule_client, schedule_id, payload)['status'] == 'ok'

  today = get_items_for_delivery(delivery)
  history = get_history_for_delivery(delivery)

  assert [item['operation_type'] for item in today['schedule_items']] == ['Order']
  assert all(
    item['operation_type'] != 'Activity' for schedule in history['schedules'] for item in schedule['schedule_items']
  )


def test_activity_does_not_keep_shared_position_open(schedule_client):  # noqa: F811
  delivery, schedule_id, payload = _setup()
  payload['schedule_items'].append(_activity())
  assert _put(schedule_client, schedule_id, payload)['status'] == 'ok'
  create(ScheduleItemUser, {'schedule_id': schedule_id, 'user_id': delivery.id, 'type': ScheduleItemUserType.OPENING})

  order_item_id = payload['schedule_items'][0]['id']
  assert update_schedule_item(delivery, order_item_id, True)['status'] == 'ok'

  assert get_latest_schedule_item_user(schedule_id).type == ScheduleItemUserType.CLOSING

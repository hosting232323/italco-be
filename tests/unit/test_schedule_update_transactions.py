from datetime import date, time, timedelta

import pytest
from database_api import Session
from database_api.operations import create
from flask import Flask
from sqlalchemy import text

import src.end_points.schedule as schedule_endpoints
from src.database.enum import ScheduleType
from src.database.schema import DeliveryUserInfo, Order, Schedule, ScheduleItem, ScheduleItemOrder, Transport, User
from src.end_points.schedule import schedule_bp
from src.end_points.schedule.queries import transport_assignment_lock_key, lock_transport_assignment
from tests.unit.factories import admin_header


@pytest.fixture
def schedule_client(seeded_db):
  app = Flask(__name__)
  app.register_blueprint(schedule_bp, url_prefix='/schedule/')
  return app.test_client()


DEFAULT_TEST_DATE = date.today() + timedelta(days=30)


def _create_schedule_with_order(transport_id: int = None, schedule_date: date = None):
  with Session() as session:
    transport_id = transport_id or session.query(Transport).first().id
    order = session.query(Order).first()
    schedule = create(
      Schedule, {'date': schedule_date or DEFAULT_TEST_DATE, 'transport_id': transport_id}, session=session
    )
    item = create(
      ScheduleItem,
      {
        'index': 0,
        'start_time_slot': time(8),
        'end_time_slot': time(10),
        'operation_type': ScheduleType.ORDER,
        'schedule_id': schedule.id,
      },
      session=session,
    )
    create(ScheduleItemOrder, {'order_id': order.id, 'schedule_item_id': item.id}, session=session)
    session.commit()
    return schedule.id, item.id, order.id, transport_id


def _payload(schedule_id, item_id, order_id, transport_id, schedule_date=None):
  return {
    'id': schedule_id,
    'date': (schedule_date or DEFAULT_TEST_DATE).isoformat(),
    'transport_id': transport_id,
    'schedule_items': [
      {
        'id': item_id,
        'index': 0,
        'operation_type': 'Order',
        'order_id': order_id,
        'start_time_slot': '08:00',
        'end_time_slot': '10:00',
      }
    ],
  }


def _free_transport_id(exclude_id: int) -> int:
  with Session() as session:
    return session.query(Transport).filter(Transport.id != exclude_id).first().id


def test_update_schedule_keeps_the_delivery_users_of_its_transport(schedule_client, monkeypatch):
  monkeypatch.setattr(schedule_endpoints, 'save_info_to_euronics', lambda _: None)
  schedule_id, item_id, order_id, transport_id = _create_schedule_with_order()

  response = schedule_client.put(
    f'/schedule/{schedule_id}',
    json=_payload(schedule_id, item_id, order_id, transport_id),
    headers=admin_header(),
  )

  assert response.get_json()['status'] == 'ok'
  with Session() as session:
    expected = {
      row[0] for row in session.query(DeliveryUserInfo.user_id).filter(DeliveryUserInfo.transport_id == transport_id)
    }
    schedule = session.query(Schedule).filter_by(id=schedule_id).one()
    assert schedule.transport_id == transport_id
    assert expected


def test_update_schedule_rejects_transport_already_busy_that_day(schedule_client):
  schedule_id, item_id, order_id, transport_id = _create_schedule_with_order()
  busy_transport_id = _free_transport_id(transport_id)
  with Session() as session:
    create(Schedule, {'date': DEFAULT_TEST_DATE, 'transport_id': busy_transport_id}, session=session)
    session.commit()

  response = schedule_client.put(
    f'/schedule/{schedule_id}',
    json=_payload(schedule_id, item_id, order_id, busy_transport_id),
    headers=admin_header(),
  )

  body = response.get_json()
  assert body['status'] == 'ko'
  assert body['message'].endswith('borderò in questa data')
  with Session() as session:
    assert session.query(Schedule).filter_by(id=schedule_id).one().transport_id == transport_id


def test_update_schedule_date_change_detects_busy_transport(schedule_client):
  schedule_id, item_id, order_id, transport_id = _create_schedule_with_order()
  busy_date = DEFAULT_TEST_DATE + timedelta(days=1)
  with Session() as session:
    create(Schedule, {'date': busy_date, 'transport_id': transport_id}, session=session)
    session.commit()

  response = schedule_client.put(
    f'/schedule/{schedule_id}',
    json=_payload(schedule_id, item_id, order_id, transport_id, schedule_date=busy_date),
    headers=admin_header(),
  )

  body = response.get_json()
  assert body['status'] == 'ko'
  assert body['message'].endswith('borderò in questa data')
  with Session() as session:
    assert session.query(Schedule).filter_by(id=schedule_id).one().date == DEFAULT_TEST_DATE


def _create_payload(transport_id, order_id, schedule_date):
  return {
    'date': schedule_date.isoformat(),
    'transport_id': transport_id,
    'schedule_items': [
      {
        'index': 0,
        'operation_type': 'Order',
        'order_id': order_id,
        'start_time_slot': '08:00',
        'end_time_slot': '10:00',
      }
    ],
  }


def test_create_schedule_rejects_transport_already_busy_that_day(schedule_client):
  work_date = date.today() + timedelta(days=40)
  with Session() as session:
    transport_id = session.query(Transport).first().id
    order_id = session.query(Order).first().id
    create(Schedule, {'date': work_date, 'transport_id': transport_id}, session=session)
    session.commit()

  response = schedule_client.post(
    '/schedule/',
    json=_create_payload(transport_id, order_id, work_date),
    headers=admin_header(),
  )

  body = response.get_json()
  assert body['status'] == 'ko'
  assert body['message'].endswith('borderò in questa data')


def test_create_schedule_ignores_users_sent_by_an_old_client(schedule_client, monkeypatch):
  """Il client vecchio manda ancora 'users': il campo si scarta, non si salva."""
  monkeypatch.setattr(schedule_endpoints, 'save_info_to_euronics', lambda _: None)
  with Session() as session:
    delivery_id = session.query(User).filter_by(nickname='delivery_1').one().id
    transport_id = session.query(Transport).first().id
    order_id = session.query(Order).first().id

  payload = _create_payload(transport_id, order_id, date.today() + timedelta(days=41))
  payload['users'] = [{'id': delivery_id}]
  response = schedule_client.post('/schedule/', json=payload, headers=admin_header())

  body = response.get_json()
  assert body['status'] == 'ok'
  with Session() as session:
    schedule = session.query(Schedule).filter_by(id=body['schedule']['id']).one()
    assert schedule.transport_id == transport_id


def test_transport_assignment_lock_blocks_concurrent_transactions():
  with Session() as first, Session() as second:
    lock_transport_assignment(7, date.today(), session=first)
    acquired = second.execute(
      text('SELECT pg_try_advisory_xact_lock(hashtext(:key))'),
      {'key': transport_assignment_lock_key(7, date.today())},
    ).scalar()
    assert acquired is False
    first.rollback()
    acquired = second.execute(
      text('SELECT pg_try_advisory_xact_lock(hashtext(:key))'),
      {'key': transport_assignment_lock_key(7, date.today())},
    ).scalar()
    assert acquired is True

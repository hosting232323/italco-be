from datetime import date, time, timedelta

import pytest
from database_api import Session
from database_api.operations import create
from flask import Flask
from sqlalchemy import text

import src.end_points.schedule as schedule_endpoints
from src.database.enum import ScheduleType
from src.database.schema import DeliveryGroup, Order, Schedule, ScheduleItem, ScheduleItemOrder, Transport, User
from src.end_points.schedule import schedule_bp
from src.end_points.schedule.queries import delivery_assignment_lock_key, lock_delivery_assignment
from src.database.enum import UserRole
from tests.unit.factories import admin_header, create_user


@pytest.fixture
def schedule_client(seeded_db):
  app = Flask(__name__)
  app.register_blueprint(schedule_bp, url_prefix='/schedule/')
  return app.test_client()


def _create_schedule_with_order(delivery: User):
  with Session() as session:
    transport = session.query(Transport).first()
    order = session.query(Order).first()
    schedule = create(Schedule, {'date': date.today(), 'transport_id': transport.id}, session=session)
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
    create(DeliveryGroup, {'schedule_id': schedule.id, 'user_id': delivery.id}, session=session)
    session.commit()
    return schedule.id, item.id, order.id, transport.id


def _payload(schedule_id, item_id, order_id, transport_id, delivery_id, schedule_date=None, deleted_users=None):
  return {
    'id': schedule_id,
    'date': (schedule_date or date.today()).isoformat(),
    'transport_id': transport_id,
    'deleted_users': [delivery_id] if deleted_users is None else deleted_users,
    'users': [{'id': delivery_id}],
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


def test_update_schedule_can_delete_and_readd_same_delivery(schedule_client, monkeypatch):
  monkeypatch.setattr(schedule_endpoints, 'save_info_to_euronics', lambda _: None)
  with Session() as session:
    delivery = session.query(User).filter_by(email='delivery_1').one()
    delivery_id = delivery.id
  schedule_id, item_id, order_id, transport_id = _create_schedule_with_order(delivery)

  response = schedule_client.put(
    f'/schedule/{schedule_id}',
    json=_payload(schedule_id, item_id, order_id, transport_id, delivery_id),
    headers=admin_header(),
  )

  assert response.get_json()['status'] == 'ok'
  with Session() as session:
    groups = session.query(DeliveryGroup).filter_by(schedule_id=schedule_id).all()
    assert [group.user_id for group in groups] == [delivery_id]


def test_update_schedule_conflict_rolls_back_deleted_delivery(schedule_client):
  with Session() as session:
    old_delivery = session.query(User).filter_by(email='delivery_1').one()
    busy_delivery = session.query(User).filter_by(email='delivery').one()
    old_delivery_id = old_delivery.id
    busy_delivery_id = busy_delivery.id
  schedule_id, item_id, order_id, transport_id = _create_schedule_with_order(old_delivery)
  with Session() as session:
    busy_schedule = create(Schedule, {'date': date.today(), 'transport_id': transport_id}, session=session)
    create(DeliveryGroup, {'schedule_id': busy_schedule.id, 'user_id': busy_delivery_id}, session=session)
    session.commit()

  payload = _payload(schedule_id, item_id, order_id, transport_id, old_delivery_id)
  payload['users'] = [{'id': busy_delivery_id}]
  response = schedule_client.put(
    f'/schedule/{schedule_id}',
    json=payload,
    headers=admin_header(),
  )

  body = response.get_json()
  assert body['status'] == 'ko'
  assert body['message'].endswith('assegnato')
  with Session() as session:
    groups = session.query(DeliveryGroup).filter_by(schedule_id=schedule_id).all()
    assert [group.user_id for group in groups] == [old_delivery_id]


def test_update_schedule_date_change_detects_busy_kept_delivery(schedule_client):
  with Session() as session:
    delivery = session.query(User).filter_by(email='delivery_1').one()
    delivery_id = delivery.id
  schedule_id, item_id, order_id, transport_id = _create_schedule_with_order(delivery)
  busy_date = date.today() + timedelta(days=1)
  with Session() as session:
    busy_schedule = create(Schedule, {'date': busy_date, 'transport_id': transport_id}, session=session)
    create(DeliveryGroup, {'schedule_id': busy_schedule.id, 'user_id': delivery_id}, session=session)
    session.commit()

  response = schedule_client.put(
    f'/schedule/{schedule_id}',
    json=_payload(schedule_id, item_id, order_id, transport_id, delivery_id, schedule_date=busy_date, deleted_users=[]),
    headers=admin_header(),
  )

  body = response.get_json()
  assert body['status'] == 'ko'
  assert body['message'].endswith('assegnato')
  with Session() as session:
    assert session.query(Schedule).filter_by(id=schedule_id).one().date == date.today()
    groups = session.query(DeliveryGroup).filter_by(schedule_id=schedule_id).all()
    assert [group.user_id for group in groups] == [delivery_id]


def test_update_schedule_date_change_checks_kept_delivery_omitted_from_payload(schedule_client):
  with Session() as session:
    kept_delivery = session.query(User).filter_by(email='delivery_1').one()
    kept_delivery_id = kept_delivery.id
  schedule_id, item_id, order_id, transport_id = _create_schedule_with_order(kept_delivery)
  new_delivery_id = create_user(UserRole.DELIVERY).id
  busy_date = date.today() + timedelta(days=1)
  with Session() as session:
    busy_schedule = create(Schedule, {'date': busy_date, 'transport_id': transport_id}, session=session)
    create(DeliveryGroup, {'schedule_id': busy_schedule.id, 'user_id': kept_delivery_id}, session=session)
    session.commit()

  payload = _payload(
    schedule_id, item_id, order_id, transport_id, kept_delivery_id, schedule_date=busy_date, deleted_users=[]
  )
  payload['users'] = [{'id': new_delivery_id}]
  response = schedule_client.put(f'/schedule/{schedule_id}', json=payload, headers=admin_header())

  body = response.get_json()
  assert body['status'] == 'ko'
  assert body['message'].endswith('assegnato')
  with Session() as session:
    assert session.query(Schedule).filter_by(id=schedule_id).one().date == date.today()
    groups = session.query(DeliveryGroup).filter_by(schedule_id=schedule_id).all()
    assert [group.user_id for group in groups] == [kept_delivery_id]


def _create_payload(transport_id, order_id, delivery_ids, schedule_date):
  return {
    'date': schedule_date.isoformat(),
    'transport_id': transport_id,
    'users': [{'id': delivery_id} for delivery_id in delivery_ids],
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


def test_create_schedule_rejects_non_delivery_user(schedule_client):
  with Session() as session:
    customer_id = session.query(User).filter_by(email='customer').one().id
    transport_id = session.query(Transport).first().id
    order_id = session.query(Order).first().id

  response = schedule_client.post(
    '/schedule/',
    json=_create_payload(transport_id, order_id, [customer_id], date.today() + timedelta(days=40)),
    headers=admin_header(),
  )

  body = response.get_json()
  assert body['status'] == 'ko'
  assert 'delivery validi' in body['message']


def test_create_schedule_deduplicates_delivery_users(schedule_client, monkeypatch):
  monkeypatch.setattr(schedule_endpoints, 'save_info_to_euronics', lambda _: None)
  with Session() as session:
    delivery_id = session.query(User).filter_by(email='delivery_1').one().id
    transport_id = session.query(Transport).first().id
    order_id = session.query(Order).first().id

  response = schedule_client.post(
    '/schedule/',
    json=_create_payload(transport_id, order_id, [delivery_id, delivery_id], date.today() + timedelta(days=41)),
    headers=admin_header(),
  )

  body = response.get_json()
  assert body['status'] == 'ok'
  with Session() as session:
    groups = session.query(DeliveryGroup).filter_by(schedule_id=body['schedule']['id']).all()
    assert [group.user_id for group in groups] == [delivery_id]


def test_delivery_group_unique_constraint_blocks_duplicates(seeded_db):
  from sqlalchemy.exc import IntegrityError

  with Session() as session:
    delivery_id = session.query(User).filter_by(email='delivery_1').one().id
    transport_id = session.query(Transport).first().id
    schedule = create(
      Schedule, {'date': date.today() + timedelta(days=42), 'transport_id': transport_id}, session=session
    )
    create(DeliveryGroup, {'schedule_id': schedule.id, 'user_id': delivery_id}, session=session)
    session.commit()
    schedule_id = schedule.id

  with pytest.raises(IntegrityError):
    with Session() as session:
      create(DeliveryGroup, {'schedule_id': schedule_id, 'user_id': delivery_id}, session=session)
      session.commit()


def test_delivery_assignment_lock_blocks_concurrent_transactions():
  with Session() as first, Session() as second:
    lock_delivery_assignment(7, date.today(), session=first)
    acquired = second.execute(
      text('SELECT pg_try_advisory_xact_lock(hashtext(:key))'),
      {'key': delivery_assignment_lock_key(7, date.today())},
    ).scalar()
    assert acquired is False
    first.rollback()
    acquired = second.execute(
      text('SELECT pg_try_advisory_xact_lock(hashtext(:key))'),
      {'key': delivery_assignment_lock_key(7, date.today())},
    ).scalar()
    assert acquired is True

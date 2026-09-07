from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from database_api import Session
from flask import Flask

import src.end_points.orders as orders_module
import src.end_points.schedule as schedule_endpoints
from src.database.enum import UserRole
from src.database.schema import Order, Transport, User
from src.end_points.orders import update_order_endpoint
from src.end_points.orders import crud as order_crud
from src.end_points.schedule import schedule_bp
from tests.unit.factories import (
  admin_header,
  create_order as factory_create_order,
  create_schedule as factory_create_schedule,
  link_order_to_schedule,
)


@pytest.fixture
def schedule_client(seeded_db):
  app = Flask(__name__)
  app.register_blueprint(schedule_bp, url_prefix='/schedule/')
  return app.test_client()


def _create_payload(transport_id, order_id, delivery_id, schedule_date):
  return {
    'date': schedule_date.isoformat(),
    'transport_id': transport_id,
    'users': [{'id': delivery_id}],
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


def test_create_schedule_sends_sms_after_successful_commit(schedule_client, monkeypatch):
  calls = []
  monkeypatch.setattr(schedule_endpoints, 'schedule_sms_check', lambda order, item: calls.append(('sms', order, item)))
  monkeypatch.setattr(schedule_endpoints, 'save_info_to_euronics', lambda _: calls.append(('euronics', None, None)))
  with Session() as session:
    delivery_id = session.query(User).filter_by(nickname='delivery_1').one().id
    transport_id = session.query(Transport).first().id
    order_id = session.query(Order).first().id

  response = schedule_client.post(
    '/schedule/',
    json=_create_payload(transport_id, order_id, delivery_id, date.today() + timedelta(days=50)),
    headers=admin_header(),
  )

  assert response.get_json()['status'] == 'ok'
  # Euronics viene sincronizzato prima degli SMS: un errore di invio non deve
  # bloccare l'allineamento dello stato ordini.
  assert [call[0] for call in calls] == ['euronics', 'sms']
  assert calls[1][1].id == order_id


def test_create_schedule_does_not_send_sms_when_transaction_fails(schedule_client, monkeypatch):
  sent = []
  monkeypatch.setattr(schedule_endpoints, 'schedule_sms_check', lambda order, item: sent.append((order, item)))

  def failing_handle_schedule_item(item, schedule, session, pending_sms):
    pending_sms.append((item.get('order'), None))
    raise RuntimeError('handling failed after sms was queued')

  monkeypatch.setattr(schedule_endpoints, 'handle_schedule_item', failing_handle_schedule_item)
  with Session() as session:
    delivery_id = session.query(User).filter_by(nickname='delivery_1').one().id
    transport_id = session.query(Transport).first().id
    order_id = session.query(Order).first().id

  response = schedule_client.post(
    '/schedule/',
    json=_create_payload(transport_id, order_id, delivery_id, date.today() + timedelta(days=51)),
    headers=admin_header(),
  )

  assert response.status_code == 500
  assert sent == []


def test_update_order_queues_sms_instead_of_sending_in_transaction(db):
  order = factory_create_order()
  schedule = factory_create_schedule()
  item = link_order_to_schedule(order, schedule)

  pending = []
  with Session() as session:
    order = session.query(Order).filter(Order.id == order.id).one()
    order_crud.update_order(
      SimpleNamespace(role=UserRole.ADMIN),
      order,
      {'id': order.id, 'start_time_slot': '11:30', 'end_time_slot': '13:30'},
      session,
      pending_sms=pending,
    )
    assert len(pending) == 1
    assert pending[0][0].id == order.id
    assert pending[0][1].id == item.id


class StubSession:
  def execute(self, _statement):
    return None

  def __init__(self, fail_commit=False):
    self.fail_commit = fail_commit

  def __call__(self):
    return self

  def __enter__(self):
    return self

  def __exit__(self, *_args):
    return None

  def commit(self):
    if self.fail_commit:
      raise RuntimeError('commit failed')


class StubEntity:
  id = 1
  version = 1

  def to_dict(self):
    return {'id': self.id}


def _run_order_update_endpoint(monkeypatch, fail_commit):
  app = Flask(__name__)
  sent = []
  monkeypatch.setattr(orders_module, 'SessionWithStorage', StubSession(fail_commit=fail_commit))
  monkeypatch.setattr(orders_module, 'get_by_id', lambda *_args, **_kwargs: StubEntity())
  monkeypatch.setattr(orders_module, 'delay_sms_check', lambda order, item: sent.append((order, item)))
  monkeypatch.setattr(orders_module, 'save_order_status_to_euronics', lambda _order: None)
  monkeypatch.setattr(orders_module, 'mailer_check', lambda *_args: None)

  def queue_sms(_user, order, _data, _session, pending_sms=None):
    pending_sms.append((order, 'schedule-item'))
    return None

  monkeypatch.setattr(orders_module, 'update_order', queue_sms)
  with app.test_request_context('/order/1', method='PUT', json={'version': 1}):
    if fail_commit:
      with pytest.raises(RuntimeError, match='commit failed'):
        update_order_endpoint.__wrapped__(SimpleNamespace(), 1)
    else:
      update_order_endpoint.__wrapped__(SimpleNamespace(), 1)
  return sent


def test_order_update_endpoint_sends_sms_after_commit(monkeypatch):
  sent = _run_order_update_endpoint(monkeypatch, fail_commit=False)
  assert len(sent) == 1


def test_order_update_endpoint_skips_sms_when_commit_fails(monkeypatch):
  sent = _run_order_update_endpoint(monkeypatch, fail_commit=True)
  assert sent == []

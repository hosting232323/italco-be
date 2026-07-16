from datetime import date, time

import src.end_points.schedule.sms_sender as sms_sender
from src.end_points.schedule.sms_sender import schedule_sms_check

from tests.unit.factories import (
  create_order,
  create_product,
  create_schedule,
  customer_with_service,
  link_order_to_schedule,
)


def test_schedule_sms_disabled_in_dev(db, monkeypatch):
  monkeypatch.setattr(sms_sender, 'IS_DEV', True)
  calls = []
  monkeypatch.setattr(sms_sender, 'send_sms', lambda *args: calls.append(args))

  schedule_sms_check(create_order(addressee_contact='+39000'), None)

  assert calls == []


def test_schedule_sms_skipped_without_contact(db, monkeypatch):
  monkeypatch.setattr(sms_sender, 'IS_DEV', False)
  calls = []
  monkeypatch.setattr(sms_sender, 'send_sms', lambda *args: calls.append(args))

  schedule_sms_check(create_order(), None)

  assert calls == []


def test_schedule_sms_sends_programmed_message(app, db, monkeypatch):
  monkeypatch.setattr(sms_sender, 'IS_DEV', False)
  monkeypatch.setenv('VONAGE_API_KEY', 'key')
  monkeypatch.setenv('VONAGE_API_SECRET', 'secret')
  sent = []
  monkeypatch.setattr(sms_sender, 'send_sms', lambda *args: sent.append(args))

  customer, _, service_user, _ = customer_with_service()
  order = create_order(addressee_contact='+39555', booking_date=date(2026, 7, 22))
  create_product(order, service_user)
  item = link_order_to_schedule(order, create_schedule(), start_time_slot=time(14, 0), end_time_slot=time(16, 0))

  with app.test_request_context(headers={'Origin': 'https://fe.example.com'}):
    schedule_sms_check(order, item)

  assert len(sent) == 1
  message = sent[0][4]
  assert 'programmata' in message
  assert '14:00' in message and '16:00' in message
  assert customer.nickname in message

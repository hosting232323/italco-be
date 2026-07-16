from datetime import date, time

import src.end_points.orders.sms_sender as sms_sender
from src.end_points.orders.sms_sender import delay_sms_check, get_order_link, hashids

from tests.unit.factories import (
  create_order,
  create_product,
  create_schedule,
  customer_with_service,
  link_order_to_schedule,
)


def test_get_order_link_uses_origin_and_hashid(app, db):
  order = create_order()

  with app.test_request_context(headers={'Origin': 'https://fe.example.com'}):
    link = get_order_link(order)

  assert link == f'https://fe.example.com/order/{hashids.encode(order.id)}'
  assert hashids.decode(link.rsplit("/", 1)[-1]) == (order.id,)


def test_delay_sms_check_disabled_in_dev(db, monkeypatch):
  monkeypatch.setattr(sms_sender, 'IS_DEV', True)
  calls = []
  monkeypatch.setattr(sms_sender, 'send_sms', lambda *args: calls.append(args))
  order = create_order(addressee_contact='+390000000')

  delay_sms_check(order, None)

  assert calls == []


def test_delay_sms_check_skipped_without_contact(db, monkeypatch):
  monkeypatch.setattr(sms_sender, 'IS_DEV', False)
  calls = []
  monkeypatch.setattr(sms_sender, 'send_sms', lambda *args: calls.append(args))

  delay_sms_check(create_order(), None)

  assert calls == []


def test_delay_sms_check_sends_message_with_slot(app, db, monkeypatch):
  monkeypatch.setattr(sms_sender, 'IS_DEV', False)
  monkeypatch.setenv('VONAGE_API_KEY', 'key')
  monkeypatch.setenv('VONAGE_API_SECRET', 'secret')
  sent = []
  monkeypatch.setattr(sms_sender, 'send_sms', lambda *args: sent.append(args))

  customer, _, service_user, _ = customer_with_service()
  order = create_order(addressee_contact='+391112223', booking_date=date(2026, 7, 20))
  create_product(order, service_user)
  item = link_order_to_schedule(
    order, create_schedule(), start_time_slot=time(9, 0), end_time_slot=time(11, 0)
  )

  with app.test_request_context(headers={'Origin': 'https://fe.example.com'}):
    delay_sms_check(order, item)

  assert len(sent) == 1
  key, secret, sender, contact, message = sent[0]
  assert (key, secret, sender, contact) == ('key', 'secret', 'Ares', '+391112223')
  assert 'riprogrammata' in message
  assert '09:00' in message and '11:00' in message
  assert customer.nickname in message

import pytest
from database_api.operations import create

import src.end_points.orders.mailer as mailer
from src.database.enum import OrderStatus
from src.database.schema import Photo
from src.end_points.orders.mailer import get_mails, get_user_mail, mailer_check

from tests.unit.factories import (
  create_customer_info,
  create_order,
  create_product,
  customer_with_service,
)


def test_mailer_check_is_disabled_in_dev(monkeypatch):
  monkeypatch.setattr(mailer, 'IS_DEV', True)
  calls = []
  monkeypatch.setattr(mailer, 'send_email', lambda *args: calls.append(args))

  mailer_check(None, {'status': OrderStatus.NOT_DELIVERED}, None)

  assert calls == []


def test_mailer_check_ignores_neutral_updates(db, monkeypatch):
  monkeypatch.setattr(mailer, 'IS_DEV', False)
  calls = []
  monkeypatch.setattr(mailer, 'send_email', lambda *args: calls.append(args))
  order = create_order()

  mailer_check(order, {'operator_note': 'niente di grave'}, None)

  assert calls == []


def test_mailer_check_sends_for_not_delivered(db, monkeypatch, tmp_path):
  monkeypatch.setattr(mailer, 'IS_DEV', False)
  sent = []
  monkeypatch.setattr(
    mailer,
    'send_email',
    lambda mail, content, subject, attachments=None, signature=None: sent.append((mail, content, subject, attachments)),
  )
  monkeypatch.setattr(mailer, 'get_full_path', lambda *_: str(tmp_path))
  (tmp_path / 'foto.jpg').write_bytes(b'contenuto-immagine')
  order = create_order(status=OrderStatus.NOT_DELIVERED, customer_note='citofonare due volte')
  create(Photo, {'order_id': order.id, 'link': 'http://x/foto.jpg'})

  mailer_check(order, {'status': OrderStatus.NOT_DELIVERED}, 'Cliente assente')

  assert len(sent) == len(mailer.MAILS)
  _, content, subject, attachments = sent[0]
  assert '❌' in subject
  assert 'non completato' in subject
  assert 'Cliente assente' in content['text']
  assert 'citofonare due volte' in content['text']
  assert attachments == [{'content': b'contenuto-immagine', 'filename': 'foto.jpg'}]
  assert 'http://x/foto.jpg' not in content['html']
  assert '1 in allegato' in content['html']


def test_mailer_check_raises_when_photo_missing_from_disk(db, monkeypatch, tmp_path):
  monkeypatch.setattr(mailer, 'IS_DEV', False)
  monkeypatch.setattr(mailer, 'get_full_path', lambda *_: str(tmp_path))
  order = create_order(status=OrderStatus.NOT_DELIVERED)
  create(Photo, {'order_id': order.id, 'link': 'http://x/sparita.jpg'})

  with pytest.raises(FileNotFoundError):
    mailer_check(order, {'status': OrderStatus.NOT_DELIVERED}, None)


def test_mailer_check_sends_for_delay_and_anomaly_flags(db, monkeypatch):
  monkeypatch.setattr(mailer, 'IS_DEV', False)
  sent = []
  monkeypatch.setattr(
    mailer, 'send_email', lambda mail, content, subject, attachments=None, signature=None: sent.append(subject)
  )
  order = create_order(status=OrderStatus.TO_RESCHEDULE)

  mailer_check(order, {'delay': True, 'anomaly': True}, None)

  subject = sent[0]
  assert 'da rischedulare' in subject
  assert 'in ritardo' in subject
  assert 'con anomalia' in subject


def test_mailer_check_without_motivation_uses_placeholder(db, monkeypatch):
  monkeypatch.setattr(mailer, 'IS_DEV', False)
  sent = []
  monkeypatch.setattr(
    mailer, 'send_email', lambda mail, content, subject, attachments=None, signature=None: sent.append(content)
  )
  order = create_order(status=OrderStatus.NOT_DELIVERED)

  mailer_check(order, {'status': OrderStatus.NOT_DELIVERED}, None)

  assert 'Nessuna motivazione fornita' in sent[0]['text']


def test_get_mails_includes_customer_email_in_prod(db, monkeypatch):
  monkeypatch.setattr(mailer, 'IS_DEV', False)
  customer, _, service_user, _ = customer_with_service()
  create_customer_info(customer, email='negozio@example.com')
  order = create_order()
  create_product(order, service_user)

  mails = get_mails(order)

  assert 'negozio@example.com' in mails
  assert set(mailer.MAILS) <= set(mails)


def test_get_mails_in_dev_returns_static_list(monkeypatch):
  monkeypatch.setattr(mailer, 'IS_DEV', True)

  assert get_mails(None) == mailer.MAILS


def test_get_user_mail_finds_customer_info(db):
  customer, _, service_user, _ = customer_with_service()
  create_customer_info(customer, email='pv@example.com')
  order = create_order()
  create_product(order, service_user)

  assert get_user_mail(order).email == 'pv@example.com'
  assert get_user_mail(create_order()) is None

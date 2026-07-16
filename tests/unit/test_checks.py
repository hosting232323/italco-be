import pytest

from src import checks
from src.database.enum import OrderStatus, UserRole
from src.database.schema import DtrDocument, FirFirstDocument, FirFourthDocument

from tests.unit.factories import (
  create_delivery_group,
  create_order,
  create_product,
  create_schedule,
  create_transport,
  create_user,
  customer_with_service,
  link_order_to_schedule,
)
from database_api import Session


@pytest.mark.parametrize('model', [DtrDocument, FirFirstDocument, FirFourthDocument])
def test_get_all_documents_strips_base_path(model, db, monkeypatch):
  from database_api.operations import create

  base = 'https://files.example.test/rae/documents/'
  # I documenti richiedono un owner valido: creiamo lo scenario minimo.
  if model is DtrDocument:
    customer = create_user(UserRole.CUSTOMER)
    from tests.unit.factories import create_rae_product

    rae_product = create_rae_product(create_order(), customer)
    create(model, {'link': f'{base}1.pdf', 'rae_product_id': rae_product.id})
    create(model, {'link': f'{base}2.pdf', 'rae_product_id': rae_product.id})
  else:
    from tests.unit.factories import create_disposal

    disposal = create_disposal()
    create(model, {'link': f'{base}1.pdf', 'disposal_id': disposal.id})
    disposal2 = create_disposal()
    create(model, {'link': f'{base}2.pdf', 'disposal_id': disposal2.id})

  result = sorted(checks.get_all_documents(model, base))

  assert result == ['1.pdf', '2.pdf']


def test_get_all_photos_excludes_missing_ids(db, monkeypatch):
  from database_api.operations import create
  from src.database.schema import Photo

  base = 'https://files.example.test/photos/'
  order = create_order()
  create(Photo, {'order_id': order.id, 'link': f'{base}keep.jpg'})
  drop = create(Photo, {'order_id': order.id, 'link': f'{base}drop.jpg'})
  monkeypatch.setattr(checks, 'MISSING_PHOTOS', [drop.id])

  result = checks.get_all_photos(base)

  assert result == ['keep.jpg']


def test_check_orders_no_user_finds_orphan_orders(db):
  # Ordine senza prodotti/service_user
  orphan = create_order(addressee='Orfano')
  _, _, service_user, _ = customer_with_service()
  linked = create_order()
  create_product(linked, service_user)

  with Session() as session:
    results = checks.check_orders_no_user(session)

  assert [entry['order_id'] for entry in results] == [orphan.id]


def test_check_orders_no_product_finds_empty_orders(db):
  empty = create_order(addressee='Vuoto')
  _, _, service_user, _ = customer_with_service()
  full = create_order()
  create_product(full, service_user)

  with Session() as session:
    results = checks.check_orders_no_product(session)

  assert [entry['order_id'] for entry in results] == [empty.id]


def test_check_schedules_flags_missing_relations(db):
  transport = create_transport()
  create_schedule(transport)  # nessun item, nessun delivery group

  with Session() as session:
    results = checks.check_schedules(session)

  assert len(results) == 1
  assert set(results[0]['missing']) == {'ScheduleItem', 'DeliveryGroup'}


def test_check_schedules_ok_when_complete(db):
  _, _, service_user, _ = customer_with_service()
  order = create_order(status=OrderStatus.SCHEDULED)
  create_product(order, service_user)
  schedule = create_schedule()
  link_order_to_schedule(order, schedule)
  create_delivery_group(create_user(UserRole.DELIVERY), schedule)

  with Session() as session:
    assert checks.check_schedules(session) == []


def test_check_history_invalid_status_detects_null_payloads(db):
  from database_api.operations import create
  from src.database.schema import History

  order = create_order()  # genera history valida
  # Payload corrotto: il valore JSON è null (None) -> cast a stringa produce 'null'
  create(History, {'order_id': order.id, 'status': {'type': 'status', 'value': None}})

  with Session() as session:
    results = checks.check_history_invalid_status(session)

  assert len(results) == 1


def test_formatters_produce_readable_lines():
  schedule_line = checks.format_schedule_issue(
    {'schedule_id': 3, 'date': '2026-07-15', 'transport_id': 9, 'missing': ['ScheduleItem']}
  )
  order_line = checks.format_order({'order_id': 7, 'addressee': 'Rossi', 'status': 'Acquired'})

  class FakeHistory:
    id = 1
    order_id = 2
    status = {'type': 'status', 'value': None}

  history_line = checks.format_history_invalid(FakeHistory())

  assert 'Schedule ID 3' in schedule_line
  assert 'Order ID 7' in order_line
  assert 'History ID 1' in history_line


def test_database_integrity_test_sends_report(db, monkeypatch):
  messages = []
  monkeypatch.setattr(checks, 'send_telegram_message', lambda text: messages.append(text))

  checks.database_integrity_test()

  assert len(messages) == 1
  assert 'Report Dati Corrotti' in messages[0]


def test_trigger_checks_orchestrates_all_steps(db, monkeypatch):
  calls = {'integrity': 0, 'mismatch': []}
  monkeypatch.setattr(checks, 'database_integrity_test', lambda: calls.__setitem__('integrity', 1))
  monkeypatch.setattr(
    checks, 'check_mismatch', lambda db_files, folder, label, subfolder: calls['mismatch'].append(label)
  )

  result = checks.trigger_checks('folder', 'photos', 'dtr', 'fir1', 'fir4')

  assert result['status'] == 'ok'
  assert calls['integrity'] == 1
  assert calls['mismatch'] == ['Photos', 'DTR Documents', 'First Copy FIR Documents', 'Fourth FIR Copy Documents']

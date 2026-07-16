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


class StubDocument:
  def __init__(self, link):
    self.link = link


class StubSession:
  def __init__(self, expected_model, links):
    self.expected_model = expected_model
    self.links = links

  def __enter__(self):
    return self

  def __exit__(self, *_):
    return None

  def query(self, model):
    assert model is self.expected_model
    return self

  def all(self):
    return [StubDocument(link) for link in self.links]


@pytest.mark.parametrize('model', [DtrDocument, FirFirstDocument, FirFourthDocument])
def test_get_all_documents_returns_basenames(model, db):
  from database_api.operations import create

  base = 'https://files.example.test/rae/documents/'
  # I documenti richiedono un owner valido: creiamo lo scenario minimo.
  if model is DtrDocument:
    from tests.unit.factories import create_rae_product

    rae_product = create_rae_product(create_order(), create_user(UserRole.CUSTOMER))
    create(model, {'link': f'{base}1.pdf', 'rae_product_id': rae_product.id})
    create(model, {'link': f'{base}2.pdf', 'rae_product_id': rae_product.id})
  else:
    from tests.unit.factories import create_disposal

    create(model, {'link': f'{base}1.pdf', 'disposal_id': create_disposal().id})
    create(model, {'link': f'{base}2.pdf', 'disposal_id': create_disposal().id})

  assert sorted(checks.get_all_documents(model)) == ['1.pdf', '2.pdf']


def test_get_all_documents_returns_basenames_for_any_prefix(monkeypatch):
  # Regressione: i link in DB possono avere host/scheme diversi da quelli della request
  # corrente (localhost, cron, http vs https): il confronto deve restare sui basename.
  links = [
    'https://ares-logistics.it/api/rae/dtr-documents/1.pdf',
    'http://localhost:8080/api/rae/dtr-documents/2.pdf',
    'https://altro-dominio.it/rae/dtr-documents/3.pdf',
    '4.pdf',
  ]
  monkeypatch.setattr(checks, 'Session', lambda: StubSession(DtrDocument, links))

  assert checks.get_all_documents(DtrDocument) == ['1.pdf', '2.pdf', '3.pdf', '4.pdf']


def test_get_all_photos_excludes_missing_ids(db, monkeypatch):
  from database_api.operations import create
  from src.database.schema import Photo

  base = 'https://files.example.test/photos/'
  order = create_order()
  create(Photo, {'order_id': order.id, 'link': f'{base}keep.jpg'})
  drop = create(Photo, {'order_id': order.id, 'link': f'{base}drop.jpg'})
  monkeypatch.setattr(checks, 'MISSING_PHOTOS', [drop.id])

  assert checks.get_all_photos() == ['keep.jpg']


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


def test_trigger_checks_passes_basenames_to_check_mismatch(monkeypatch):
  calls = []
  monkeypatch.setattr(checks, 'database_integrity_test', lambda: None)
  monkeypatch.setattr(checks, 'get_all_photos', lambda: ['1.jpg'])
  monkeypatch.setattr(checks, 'get_all_documents', lambda model: [f'{model.__name__}.pdf'])
  monkeypatch.setattr(
    checks,
    'check_mismatch',
    lambda files, folder, label, subfolder=None: calls.append((files, folder, label, subfolder)),
  )

  response = checks.trigger_checks('/static')

  assert response == {'status': 'ok', 'message': 'Check eseguiti con successo'}
  assert calls == [
    (['1.jpg'], '/static', 'Photos', 'photos'),
    (['DtrDocument.pdf'], '/static', 'DTR Documents', 'dtr-documents'),
    (['FirFirstDocument.pdf'], '/static', 'First Copy FIR Documents', 'fir-first-document'),
    (['FirFourthDocument.pdf'], '/static', 'Fourth FIR Copy Documents', 'fir-fourth-document'),
  ]

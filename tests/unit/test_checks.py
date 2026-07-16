import pytest

from src import checks
from src.database.schema import DtrDocument, FirFirstDocument, FirFourthDocument


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
def test_get_all_documents_uses_the_requested_model(monkeypatch, model):
  links = ['https://files.example.test/rae/documents/1.pdf', 'https://files.example.test/rae/documents/2.pdf']
  monkeypatch.setattr(checks, 'Session', lambda: StubSession(model, links))

  assert checks.get_all_documents(model) == ['1.pdf', '2.pdf']


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

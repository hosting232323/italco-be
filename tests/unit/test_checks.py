import pytest

from src import checks
from src.database.schema import DtrDocument, FirFirstDocument, FirFourthDocument


class StubDocument:
  def __init__(self, link):
    self.link = link


class StubSession:
  def __init__(self, expected_model):
    self.expected_model = expected_model

  def __enter__(self):
    return self

  def __exit__(self, *_):
    return None

  def query(self, model):
    assert model is self.expected_model
    return self

  def all(self):
    return [
      StubDocument('https://files.example.test/rae/documents/1.pdf'),
      StubDocument('https://files.example.test/rae/documents/2.pdf'),
    ]


@pytest.mark.parametrize('model', [DtrDocument, FirFirstDocument, FirFourthDocument])
def test_get_all_documents_uses_the_requested_model(monkeypatch, model):
  monkeypatch.setattr(checks, 'Session', lambda: StubSession(model))

  assert checks.get_all_documents(model, 'https://files.example.test/rae/documents/') == ['1.pdf', '2.pdf']

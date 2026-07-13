import pytest

from src.end_points.exportation import disposal as export_disposal_module
from src.end_points.rae import disposal as disposal_module


class StubEntity:
  def __init__(self, id):
    self.id = id

  def to_dict(self):
    return {'id': self.id}


def test_format_query_result_sums_groups_and_deduplicates_disposals():
  rows = [
    (StubEntity(7), StubEntity(10), StubEntity(20), None, None, 'R3', 3),
    (StubEntity(7), StubEntity(10), StubEntity(20), None, None, 'R1', 2),
    (StubEntity(7), StubEntity(10), StubEntity(20), None, None, 'R1', 4),
  ]
  result = []
  for row in rows:
    result = disposal_module.format_query_result(row, result)

  assert len(result) == 1
  assert result[0]['group_quantities'] == {'R1': 6, 'R3': 3}


def test_format_query_result_handles_disposal_without_products():
  result = disposal_module.format_query_result(
    (StubEntity(7), StubEntity(10), StubEntity(20), None, None, None, None), []
  )

  assert result[0]['group_quantities'] == {}


def test_get_rae_disposals_includes_automatic_group_quantities(monkeypatch):
  query_calls = 0

  def query_rae_disposals():
    nonlocal query_calls
    query_calls += 1
    return [
      (StubEntity(7), StubEntity(10), StubEntity(20), None, None, 'R1', 2),
      (StubEntity(7), StubEntity(10), StubEntity(20), None, None, 'R1', 3),
      (StubEntity(7), StubEntity(10), StubEntity(20), None, None, 'R3', 4),
    ]

  monkeypatch.setattr(disposal_module, 'query_rae_disposals', query_rae_disposals)

  result = disposal_module.get_rae_disposals()

  assert result['rae_disposals'][0]['group_quantities'] == {'R1': 5, 'R3': 4}
  assert query_calls == 1


def test_attached_b_export_reuses_disposal_query_and_formatter(monkeypatch):
  row = (StubEntity(7), StubEntity(10), StubEntity(20), None, None, 'R1', 5)
  calls = {'query': [], 'format': 0}
  rendered = {}

  def query_rae_disposals(disposal_id):
    calls['query'].append(disposal_id)
    return [row]

  def format_query_result(query_row, disposals):
    assert query_row is row
    calls['format'] += 1
    disposals.append({'id': 7, 'group_quantities': {'R1': 5}})
    return disposals

  def render_template(template, **context):
    rendered.update(template=template, **context)
    return '<html></html>'

  class PdfStatus:
    err = False

  monkeypatch.setattr(export_disposal_module, 'query_rae_disposals', query_rae_disposals)
  monkeypatch.setattr(export_disposal_module, 'format_query_result', format_query_result)
  monkeypatch.setattr(export_disposal_module, 'render_template', render_template)
  monkeypatch.setattr(export_disposal_module.pisa, 'CreatePDF', lambda **_kwargs: PdfStatus())
  monkeypatch.setattr(export_disposal_module, 'export_pdf', lambda content: content)

  export_disposal_module.export_disposal_attached_b(7)

  assert calls == {'query': [7], 'format': 1}
  assert rendered['template'] == 'disposal_attached_b.html'
  assert rendered['disposal']['id'] == 7
  assert rendered['rows'] == [{'raggruppamento': 'R1', 'quantita': 5}]
  assert rendered['total'] == 5


@pytest.mark.parametrize('disposals', [[], [{'id': 7}, {'id': 8}]])
def test_attached_b_export_rejects_invalid_disposal_count(monkeypatch, disposals):
  monkeypatch.setattr(export_disposal_module, 'query_rae_disposals', lambda _disposal_id: [object()])
  monkeypatch.setattr(export_disposal_module, 'format_query_result', lambda _row, _results: disposals)

  assert export_disposal_module.export_disposal_attached_b(7) == {
    'status': 'ko',
    'message': 'Numero di smaltimenti trovati non valido',
  }

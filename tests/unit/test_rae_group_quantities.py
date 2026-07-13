from src.end_points.rae import disposal as disposal_module
from src.end_points.rae.product_group import group_quantities_by_disposal


class StubEntity:
  def __init__(self, id):
    self.id = id

  def to_dict(self):
    return {'id': self.id}


def test_group_quantities_by_disposal_sums_and_sorts_groups():
  rows = [
    (2, 'R2', 3),
    (1, 'R4', 1),
    (1, 'R1', 2),
    (1, 'R1', 4),
    (2, 'R1', None),
  ]

  assert group_quantities_by_disposal(rows) == {
    1: {'R1': 6, 'R4': 1},
    2: {'R1': 0, 'R2': 3},
  }


def test_group_quantities_by_disposal_returns_empty_mapping_without_rows():
  assert group_quantities_by_disposal([]) == {}


def test_get_rae_disposals_includes_automatic_group_quantities(monkeypatch):
  monkeypatch.setattr(
    disposal_module,
    'query_rae_disposals',
    lambda: [(StubEntity(7), StubEntity(10), StubEntity(20))],
  )
  monkeypatch.setattr(
    disposal_module,
    'query_disposal_group_quantities',
    lambda: [(7, 'R1', 2), (7, 'R3', 4)],
  )

  result = disposal_module.get_rae_disposals()

  assert result['rae_disposals'][0]['group_quantities'] == {'R1': 2, 'R3': 4}

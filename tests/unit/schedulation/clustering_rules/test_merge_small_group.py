from src.schedulation.clustering_rules import ClusteringContext
from src.schedulation.clustering_rules.merge_small_group import (
  MergeSmallGroupsRule,
  get_group_centroid,
  merge_small_groups,
)

from tests.unit.schedulation.conftest import count_orders


def _group(order_ids, cap='70121'):
  return [
    {'operation_type': 'Order', 'order_id': order_id, 'cap': cap, 'index': index}
    for index, order_id in enumerate(order_ids)
  ]


def test_get_group_centroid_averages_coordinates():
  group = [{'cap': '70121'}, {'cap': '70122'}]

  lat, lon = get_group_centroid(group)

  assert lat is not None and lon is not None


def test_get_group_centroid_none_for_empty_group():
  assert get_group_centroid([]) == (None, None)


def test_get_group_centroid_raises_for_unknown_cap():
  import pytest

  with pytest.raises(ValueError, match='CAP 00000 not found'):
    get_group_centroid([{'cap': '00000'}])


def test_merge_small_groups_combines_nearby_small_groups():
  groups = [_group([1], '70121'), _group([2], '70122')]

  merged = merge_small_groups(groups, min_size_group=2, max_size_group=4, max_distance_km=50)

  assert len(merged) == 1
  assert count_orders(merged[0]) == 2


def test_merge_small_groups_keeps_large_groups_untouched():
  large = _group([1, 2, 3])
  small = _group([4], '70122')

  merged = merge_small_groups([large, small], min_size_group=2, max_size_group=5, max_distance_km=50)

  # Il gruppo grande resta invariato, il piccolo resta separato (nessun altro con cui unirsi)
  assert any(count_orders(group) == 3 for group in merged)
  assert any(count_orders(group) == 1 for group in merged)


def test_merge_small_groups_respects_max_size():
  groups = [_group([1, 2], '70121'), _group([3, 2], '70122')]

  merged = merge_small_groups(groups, min_size_group=3, max_size_group=3, max_distance_km=50)

  # Unire darebbe 4 > max_size=3, quindi restano separati
  assert all(count_orders(group) <= 3 for group in merged)


def test_rule_delegates_to_merge_small_groups():
  rule = MergeSmallGroupsRule()
  context = ClusteringContext(min_size_group=2, max_size_group=4, max_distance_km=50)

  result = rule.apply([_group([1], '70121'), _group([2], '70122')], context)

  assert len(result) == 1

from src.schedulation.building import build_schedule_items
from src.schedulation.clustering_rules import ClusteringContext
from src.schedulation.clustering_rules.split_large_group import (
  SplitLargeGroupsRule,
  cluster_orders_by_cap,
  enforce_max_size,
  merge_small_sub_groups,
  split_large_groups,
  split_sequentially,
)

from tests.unit.schedulation.conftest import count_orders, make_order


# CAP baresi reali con coordinate note, geograficamente vicini/lontani
NEAR_CAPS = ['70121', '70122', '70123', '70124', '70125', '70126']
FAR_CAP = '71010'  # zona diversa, distante


def _order_items(count, cap='70056'):
  orders = [make_order(i, cap, collection_point_id=i) for i in range(1, count + 1)]
  return build_schedule_items(orders)


def test_split_large_groups_keeps_group_within_limit():
  group = _order_items(2)

  result = split_large_groups([group], min_size_group=1, max_size_group=5, max_distance_km=50)

  assert len(result) == 1
  assert count_orders(result[0]) == 2


def test_split_large_groups_splits_oversized_group():
  group = _order_items(5, cap='70056')

  result = split_large_groups([group], min_size_group=1, max_size_group=2, max_distance_km=500)

  assert len(result) >= 3
  assert all(count_orders(sub) <= 2 for sub in result)
  assert sum(count_orders(sub) for sub in result) == 5


def test_enforce_max_size_rechunks_groups():
  group = _order_items(5, cap='70056')

  result = enforce_max_size([group], max_size_group=2)

  assert all(count_orders(sub) <= 2 for sub in result)
  assert sum(count_orders(sub) for sub in result) == 5


def test_split_sequentially_chunks_orders():
  orders = [{'operation_type': 'Order', 'order_id': i, 'cap': '70056', 'products': {}} for i in range(1, 6)]

  result = split_sequentially(orders, [], max_size_group=2)

  assert [count_orders(sub) for sub in result] == [2, 2, 1]


def test_rule_reindexes_after_split():
  group = _order_items(4, cap='70056')

  result = SplitLargeGroupsRule().apply(
    [group], ClusteringContext(min_size_group=1, max_size_group=2, max_distance_km=500)
  )

  for sub_group in result:
    assert [item['index'] for item in sub_group] == list(range(len(sub_group)))


def _order_with_caps(orders_spec):
  """orders_spec: lista di (order_id, cap). Costruisce gli schedule items."""
  orders = [make_order(oid, cap, collection_point_id=oid) for oid, cap in orders_spec]
  return build_schedule_items(orders)


def test_cluster_orders_by_cap_groups_nearby_orders():
  order_items = [
    {'operation_type': 'Order', 'order_id': i, 'cap': NEAR_CAPS[i % len(NEAR_CAPS)], 'products': {}} for i in range(6)
  ]

  sub_groups = cluster_orders_by_cap(order_items, [], max_size_group=3, max_distance_km=50)

  assert all(count_orders(group) <= 3 for group in sub_groups)
  assert sum(count_orders(group) for group in sub_groups) == 6


def test_cluster_orders_by_cap_respects_max_distance():
  # Ordini vicini + uno lontano: quello lontano finisce in un sottogruppo separato
  order_items = [
    {'operation_type': 'Order', 'order_id': 1, 'cap': '70121', 'products': {}},
    {'operation_type': 'Order', 'order_id': 2, 'cap': '70122', 'products': {}},
    {'operation_type': 'Order', 'order_id': 3, 'cap': FAR_CAP, 'products': {}},
  ]

  sub_groups = cluster_orders_by_cap(order_items, [], max_size_group=5, max_distance_km=1)

  assert sum(count_orders(group) for group in sub_groups) == 3
  assert len(sub_groups) >= 2


def test_merge_small_sub_groups_merges_below_min():
  first = [{'operation_type': 'Order', 'order_id': 1, 'cap': '70121', 'products': {}}]
  second = [{'operation_type': 'Order', 'order_id': 2, 'cap': '70122', 'products': {}}]

  result = merge_small_sub_groups([first, second], min_size_group=2, max_size_group=4)

  assert len(result) == 1
  assert count_orders(result[0]) == 2


def test_merge_small_sub_groups_keeps_single_group():
  single = [{'operation_type': 'Order', 'order_id': 1, 'cap': '70121', 'products': {}}]

  assert merge_small_sub_groups([single], min_size_group=2, max_size_group=4) == [single]


def test_split_large_groups_merges_undersized_subgroups():
  group = _order_with_caps([(i, NEAR_CAPS[i % len(NEAR_CAPS)]) for i in range(6)])

  result = split_large_groups([group], min_size_group=2, max_size_group=2, max_distance_km=50)

  assert sum(count_orders(sub) for sub in result) == 6
  assert all(count_orders(sub) <= 2 for sub in result)

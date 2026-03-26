from src.end_points.schedule import clustering as clustering_module
from src.end_points.schedule import experiments as experiments_module
from src.end_points.schedule import schedulation as schedulation_module
from src.end_points.schedule.clustering import (
  ClusteringRuleFactory,
  MergeSmallGroupsRule,
  SplitLargeGroupsRule,
)


def _make_order(order_id: int, cap: str, collection_point_id: int | None = None) -> dict:
  collection_point_id = collection_point_id or order_id
  return {
    'id': order_id,
    'cap': cap,
    'address': f'Order {order_id}',
    'products': {
      f'product-{order_id}': {
        'collection_point': {
          'id': collection_point_id,
          'cap': cap,
          'address': f'Collection point {collection_point_id}',
        },
      },
    },
  }


def _patch_cap_lookup(monkeypatch, coords: dict[str, tuple[float, float]]):
  def cap_lookup(cap: str) -> tuple[float, float]:
    return coords[cap]

  monkeypatch.setattr(clustering_module, 'get_lat_lon_by_cap', cap_lookup)
  monkeypatch.setattr(experiments_module, 'get_lat_lon_by_cap', cap_lookup)
  monkeypatch.setattr(schedulation_module, 'get_lat_lon_by_cap', cap_lookup)


def _order_ids(group: dict) -> list[int]:
  return [item['order_id'] for item in group['schedule_items'] if item['operation_type'] == 'Order']


def test_clustering_rule_factory_builds_default_rules():
  rules = ClusteringRuleFactory().build()

  assert [type(rule) for rule in rules] == [MergeSmallGroupsRule, SplitLargeGroupsRule]


def test_build_clustered_schedule_item_groups_merges_small_groups(monkeypatch):
  _patch_cap_lookup(
    monkeypatch,
    {
      '10000': (41.0, 16.0),
      '10001': (41.001, 16.001),
    },
  )

  groups = schedulation_module.build_clustered_schedule_item_groups(
    orders=[
      _make_order(1, '10000'),
      _make_order(2, '10001'),
    ],
    min_size_group=2,
    max_size_group=2,
    max_distance_km=5,
  )

  assert len(groups) == 1
  assert len([item for item in groups[0] if item['operation_type'] == 'Order']) == 2


def test_build_clustered_schedule_item_groups_splits_large_groups(monkeypatch):
  _patch_cap_lookup(
    monkeypatch,
    {
      '10000': (41.0, 16.0),
    },
  )

  groups = schedulation_module.build_clustered_schedule_item_groups(
    orders=[
      _make_order(1, '10000', collection_point_id=10),
      _make_order(2, '10000', collection_point_id=11),
      _make_order(3, '10000', collection_point_id=12),
    ],
    min_size_group=1,
    max_size_group=2,
    max_distance_km=5,
  )

  assert len(groups) == 2
  assert sorted(len([item for item in group if item['operation_type'] == 'Order']) for group in groups) == [1, 2]


def test_assign_orders_to_groups_preserves_delivery_assignment(monkeypatch):
  _patch_cap_lookup(
    monkeypatch,
    {
      '10000': (41.0, 16.0),
      '20000': (42.0, 17.0),
      '90000': (41.0, 16.001),
      '90001': (42.0, 17.001),
    },
  )

  groups = schedulation_module.assign_orders_to_groups(
    orders=[
      _make_order(1, '10000'),
      _make_order(2, '20000'),
    ],
    delivery_users=[
      {'id': 11, 'delivery_user_info': {'cap': '90000'}},
      {'id': 22, 'delivery_user_info': {'cap': '90001'}},
    ],
    min_size_group=1,
    max_size_group=2,
    max_distance_km=5,
  )

  assignment_by_order = {tuple(_order_ids(group)): [user['id'] for user in group['delivery_users']] for group in groups}

  assert assignment_by_order == {
    (1,): [11],
    (2,): [22],
  }
  assert all(group['transports'] == [] for group in groups)

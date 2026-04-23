from src import schedulation as schedulation_module

from src.schedulation.clustering import ClusteringRuleFactory
from src.schedulation.clustering_rules.merge_small_group import MergeSmallGroupsRule
from src.schedulation.clustering_rules.split_large_group import SplitLargeGroupsRule
from src.schedulation.clustering_rules.professional_services_limit import ProfessionalServicesLimitRule


def _make_order(
  order_id: int,
  cap: str,
  collection_point_id: int | None = None,
  services: list[dict] | None = None,
) -> dict:
  collection_point_id = collection_point_id or order_id
  return {
    'id': order_id,
    'cap': cap,
    'address': f'Order {order_id}',
    'status': 'Booked',
    'dpc': None,
    'drc': None,
    'products': {
      f'product-{order_id}': {
        'collection_point': {
          'id': collection_point_id,
          'cap': cap,
          'address': f'Collection point {collection_point_id}',
        },
        'services': services or [],
      },
    },
  }


def _patch_cap_lookup(monkeypatch, coords: dict[str, tuple[float, float]]):
  def cap_lookup(cap: str) -> tuple[float, float]:
    return coords[cap]

  monkeypatch.setattr(schedulation_module, 'get_lat_lon_by_cap', cap_lookup)


def _order_ids(group: dict) -> list[int]:
  return [item['order_id'] for item in group['schedule_items'] if item['operation_type'] == 'Order']


def test_clustering_rule_factory_builds_default_rules():
  rules = ClusteringRuleFactory().build()

  assert [type(rule) for rule in rules] == [MergeSmallGroupsRule, SplitLargeGroupsRule, ProfessionalServicesLimitRule]


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


def test_professional_services_limit_rule_keeps_group_within_limit(monkeypatch):
  _patch_cap_lookup(monkeypatch, {'10000': (41.0, 16.0)})

  # 2 orders, each with 1 distinct professional service → total 2 → keep as 1 group
  groups = schedulation_module.build_clustered_schedule_item_groups(
    orders=[
      _make_order(1, '10000', services=[{'id': 10, 'name': 'SrvA', 'professional': True}]),
      _make_order(2, '10000', services=[{'id': 11, 'name': 'SrvB', 'professional': True}]),
    ],
    min_size_group=1,
    max_size_group=10,
    max_distance_km=500,
  )

  assert len(groups) == 1
  assert len([item for g in groups for item in g if item['operation_type'] == 'Order']) == 2


def test_professional_services_limit_rule_splits_when_exceeds_limit(monkeypatch):
  _patch_cap_lookup(monkeypatch, {'10000': (41.0, 16.0)})

  # 3 orders each with a distinct professional service → must split into 2 groups
  groups = schedulation_module.build_clustered_schedule_item_groups(
    orders=[
      _make_order(1, '10000', services=[{'id': 10, 'name': 'SrvA', 'professional': True}]),
      _make_order(2, '10000', services=[{'id': 11, 'name': 'SrvB', 'professional': True}]),
      _make_order(3, '10000', services=[{'id': 12, 'name': 'SrvC', 'professional': True}]),
    ],
    min_size_group=1,
    max_size_group=10,
    max_distance_km=500,
  )

  assert len(groups) == 2
  # No empty groups
  assert all(any(item['operation_type'] == 'Order' for item in g) for g in groups)
  # Each group has at most 2 professional orders (orders with ≥1 professional service)
  for g in groups:
    pro_order_count = sum(
      1
      for item in g
      if item['operation_type'] == 'Order'
      and any(
        isinstance(svc, dict) and svc.get('professional')
        for product in item.get('products', {}).values()
        for svc in product.get('services', [])
      )
    )
    assert pro_order_count <= 2


def test_professional_services_limit_rule_non_professional_services_ignored(monkeypatch):
  _patch_cap_lookup(monkeypatch, {'10000': (41.0, 16.0)})

  # 3 orders with only non-professional services → no split needed
  groups = schedulation_module.build_clustered_schedule_item_groups(
    orders=[
      _make_order(1, '10000', services=[{'id': 10, 'name': 'SrvA', 'professional': False}]),
      _make_order(2, '10000', services=[{'id': 11, 'name': 'SrvB', 'professional': False}]),
      _make_order(3, '10000', services=[{'id': 12, 'name': 'SrvC', 'professional': False}]),
    ],
    min_size_group=1,
    max_size_group=10,
    max_distance_km=500,
  )

  assert len(groups) == 1
  assert len([item for g in groups for item in g if item['operation_type'] == 'Order']) == 3


def test_professional_services_limit_rule_rebalances_after_uneven_split(monkeypatch):
  """
  With 20 orders (3 pro, 17 non-pro), min=9, max=12:
  SplitLargeGroupsRule produces [12, 8] because 8 can't be merged back (8+12=20 > max=12).
  PSLimit must rebalance to [10, 10]: 2 pro+8 non-pro and 1 pro+9 non-pro.
  Both groups must be ≥ min=9.
  """
  _patch_cap_lookup(monkeypatch, {'70020': (41.0, 16.0)})

  pro_service = [{'id': 99, 'name': 'ProfSrv', 'professional': True}]
  non_pro_service = [{'id': 1, 'name': 'NormalSrv', 'professional': False}]

  orders = [_make_order(i, '70020', collection_point_id=i, services=pro_service) for i in range(1, 4)] + [
    _make_order(i, '70020', collection_point_id=i, services=non_pro_service) for i in range(4, 21)
  ]

  groups = schedulation_module.build_clustered_schedule_item_groups(
    orders=orders,
    min_size_group=9,
    max_size_group=12,
    max_distance_km=500,
  )

  order_counts = sorted(sum(1 for item in g if item['operation_type'] == 'Order') for g in groups)

  # Should produce exactly 2 groups, each with ≥ min=9 orders
  assert len(groups) == 2, f'Expected 2 groups, got {len(groups)} with sizes {order_counts}'
  assert all(c >= 9 for c in order_counts), f'A group is smaller than min=9: {order_counts}'

  # Each group must have ≤ 2 professional orders
  for g in groups:
    pro_count = sum(
      1
      for item in g
      if item['operation_type'] == 'Order'
      and any(
        isinstance(svc, dict) and svc.get('professional')
        for product in item.get('products', {}).values()
        for svc in product.get('services', [])
      )
    )
    assert pro_count <= 2, f'Group has {pro_count} professional orders (limit 2)'

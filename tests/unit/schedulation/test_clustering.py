from src.schedulation.clustering import (
  ClusteringRuleFactory,
  ScheduleClusteringPipeline,
  build_clustered_schedule_item_groups,
)
from src.schedulation.clustering_rules import ClusteringContext
from src.schedulation.clustering_rules.merge_small_group import MergeSmallGroupsRule
from src.schedulation.clustering_rules.professional_services_limit import ProfessionalServicesLimitRule
from src.schedulation.clustering_rules.split_large_group import SplitLargeGroupsRule

from tests.unit.schedulation.conftest import count_orders, make_order


PRO = [{'id': 1, 'name': 'Pro', 'professional': True}]


def test_factory_builds_rules_in_documented_order():
  rules = ClusteringRuleFactory().build()

  assert [type(rule) for rule in rules] == [
    MergeSmallGroupsRule,
    SplitLargeGroupsRule,
    ProfessionalServicesLimitRule,
  ]


def test_pipeline_merges_small_groups():
  groups = build_clustered_schedule_item_groups(
    orders=[make_order(1, '70121'), make_order(2, '70122')],
    min_size_group=2,
    max_size_group=2,
    max_distance_km=50,
  )

  assert len(groups) == 1
  assert count_orders(groups[0]) == 2


def test_pipeline_splits_large_groups():
  groups = build_clustered_schedule_item_groups(
    orders=[make_order(i, '70056', collection_point_id=i) for i in range(1, 4)],
    min_size_group=1,
    max_size_group=2,
    max_distance_km=500,
  )

  assert len(groups) == 2
  assert sorted(count_orders(group) for group in groups) == [1, 2]


def test_pipeline_applies_professional_limit():
  groups = build_clustered_schedule_item_groups(
    orders=[
      make_order(1, '70056', collection_point_id=1, services=PRO),
      make_order(2, '70056', collection_point_id=2, services=PRO),
      make_order(3, '70056', collection_point_id=3, services=PRO),
    ],
    min_size_group=1,
    max_size_group=10,
    max_distance_km=500,
  )

  assert len(groups) == 2


def test_pipeline_cluster_uses_context():
  pipeline = ScheduleClusteringPipeline()
  context = ClusteringContext(min_size_group=1, max_size_group=5, max_distance_km=50)

  groups = pipeline.cluster([make_order(1, '70121')], context)

  assert count_orders(groups[0]) == 1

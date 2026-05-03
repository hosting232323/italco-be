from __future__ import annotations

from typing import Any
from collections import defaultdict
from dataclasses import dataclass, field

from .building import build_schedule_items
from .clustering_rules import ClusteringRule, ClusteringContext, ScheduleItemGroup

from .clustering_rules.merge_small_group import MergeSmallGroupsRule
from .clustering_rules.split_large_group import SplitLargeGroupsRule
from .clustering_rules.professional_services_limit import ProfessionalServicesLimitRule


def build_clustered_schedule_item_groups(orders, min_size_group, max_size_group, max_distance_km):
  clustering_pipeline = ScheduleClusteringPipeline()
  return clustering_pipeline.cluster(
    orders,
    context=ClusteringContext(
      min_size_group=min_size_group,
      max_size_group=max_size_group,
      max_distance_km=max_distance_km,
    ),
  )


@dataclass(frozen=True, slots=True)
class ClusteringRuleFactory:
  rules: tuple[type[ClusteringRule], ...] = (
    MergeSmallGroupsRule,
    SplitLargeGroupsRule,
    ProfessionalServicesLimitRule,
  )

  def build(self) -> list[ClusteringRule]:
    return [rule() for rule in self.rules]


class ScheduleItemGroupBuilder:
  def build(
    self,
    orders: list[dict[str, Any]],
  ) -> list[ScheduleItemGroup]:
    schedule_item_groups = []
    for group in find_cap_groups(orders):
      group_orders = [order for order in orders if get_order_caps(order) & group]
      schedule_item_groups.append(build_schedule_items(group_orders))
    return schedule_item_groups


@dataclass(slots=True)
class ScheduleClusteringPipeline:
  group_builder: ScheduleItemGroupBuilder = field(default_factory=ScheduleItemGroupBuilder)
  rule_factory: ClusteringRuleFactory = field(default_factory=ClusteringRuleFactory)

  def cluster(
    self,
    orders: list[dict[str, Any]],
    context: ClusteringContext,
  ) -> list[ScheduleItemGroup]:
    schedule_item_groups = self.group_builder.build(orders)
    for rule in self.rule_factory.build():
      schedule_item_groups = rule.apply(schedule_item_groups, context)
    return schedule_item_groups


def find_cap_groups(orders):
  groups = []
  visited = set()
  graph = build_cap_graph(orders)
  for cap in graph:
    if cap not in visited:
      stack = [cap]
      group = set()
      while stack:
        current = stack.pop()
        if current not in visited:
          visited.add(current)
          group.add(current)
          stack.extend(graph[current] - visited)
      groups.append(group)
  return groups


def build_cap_graph(orders):
  graph = defaultdict(set)
  for order in orders:
    caps = get_order_caps(order)
    for cap in caps:
      graph[cap].update(caps - {cap})
  return graph


def get_order_caps(order: dict[str, Any]) -> set[str]:
  return {product['collection_point']['cap'] for product in order['products'].values()}

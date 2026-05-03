from __future__ import annotations

from typing import Any
from dataclasses import dataclass, field

from .building import ScheduleItemGroupBuilder
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

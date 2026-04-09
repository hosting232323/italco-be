from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, TypeAlias

from geopy.distance import geodesic

from ...utils.caps import get_lat_lon_by_cap
from .experiments import split_large_groups


ScheduleItem: TypeAlias = dict[str, Any]
ScheduleItemGroup: TypeAlias = list[ScheduleItem]
ScheduleItemBuilder: TypeAlias = Callable[[list[dict[str, Any]]], ScheduleItemGroup]


@dataclass(frozen=True, slots=True)
class ClusteringContext:
  min_size_group: int
  max_size_group: int
  max_distance_km: float
  max_professional_services: int | None = None


class ClusteringRule(ABC):
  @abstractmethod
  def apply(
    self,
    schedule_item_groups: list[ScheduleItemGroup],
    context: ClusteringContext,
  ) -> list[ScheduleItemGroup]:
    raise NotImplementedError


class MergeSmallGroupsRule(ClusteringRule):
  def apply(
    self,
    schedule_item_groups: list[ScheduleItemGroup],
    context: ClusteringContext,
  ) -> list[ScheduleItemGroup]:
    return merge_small_groups(
      schedule_item_groups,
      context.min_size_group,
      context.max_size_group,
      context.max_distance_km,
    )


class SplitLargeGroupsRule(ClusteringRule):
  def apply(
    self,
    schedule_item_groups: list[ScheduleItemGroup],
    context: ClusteringContext,
  ) -> list[ScheduleItemGroup]:
    return split_large_groups(
      schedule_item_groups,
      context.min_size_group,
      context.max_size_group,
      context.max_distance_km,
    )


class ProfessionalServicesLimitRule(ClusteringRule):
  def apply(
    self,
    schedule_item_groups: list[ScheduleItemGroup],
    context: ClusteringContext,
  ) -> list[ScheduleItemGroup]:
    max_professional = getattr(context, 'max_professional_services', None)
    if max_professional is None:
      return schedule_item_groups

    new_groups: list[ScheduleItemGroup] = []
    for group in schedule_item_groups:
      cp_items = [item for item in group if item['operation_type'] == 'CollectionPoint']
      order_items = [item for item in group if item['operation_type'] == 'Order']
      if not order_items:
        new_groups.append(group)
        continue

      current_orders: list[ScheduleItem] = []
      current_prof_count = 0
      for order_item in order_items:
        prof_count = 0
        for product in order_item.get('products', {}).values():
          for service in product.get('services', []):
            if service.get('professional'):
              prof_count += 1

        if current_orders and current_prof_count + prof_count > max_professional:
          cp_ids = set()
          for o in current_orders:
            for p in o.get('products', {}).values():
              cp = p.get('collection_point')
              if cp and 'id' in cp:
                cp_ids.add(cp['id'])

          cp_for_group = [cp for cp in cp_items if cp.get('collection_point_id') in cp_ids]
          new_groups.append(cp_for_group + current_orders)
          current_orders = []
          current_prof_count = 0

        current_orders.append(order_item)
        current_prof_count += prof_count

      if current_orders:
        cp_ids = set()
        for o in current_orders:
          for p in o.get('products', {}).values():
            cp = p.get('collection_point')
            if cp and 'id' in cp:
              cp_ids.add(cp['id'])
        cp_for_group = [cp for cp in cp_items if cp.get('collection_point_id') in cp_ids]
        new_groups.append(cp_for_group + current_orders)

    return new_groups


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
    build_schedule_items: ScheduleItemBuilder,
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
    build_schedule_items: ScheduleItemBuilder,
    context: ClusteringContext,
  ) -> list[ScheduleItemGroup]:
    schedule_item_groups = self.group_builder.build(orders, build_schedule_items)
    for rule in self.rule_factory.build():
      schedule_item_groups = rule.apply(schedule_item_groups, context)
    return schedule_item_groups


def merge_small_groups(schedule_item_groups, min_size_group, max_size_group, max_distance_km):
  small_groups = []
  large_groups = []
  for group in schedule_item_groups:
    length = len([item for item in group if item['operation_type'] == 'Order'])
    if length < min_size_group:
      lat, lon = get_group_centroid(group)
      if lat is not None and lon is not None:
        small_groups.append({'group': group, 'centroid': (lat, lon), 'merged': False, 'length': length})
    else:
      large_groups.append(group)

  merged_groups = []
  for first_index, first_group in enumerate(small_groups):
    if first_group['merged']:
      continue

    first_group['merged'] = True
    for second_index, second_group in enumerate(small_groups):
      if (
        first_index != second_index
        and not second_group['merged']
        and first_group['length'] + second_group['length'] <= max_size_group
        and geodesic(first_group['centroid'], second_group['centroid']).kilometers <= max_distance_km
      ):
        second_group['merged'] = True
        first_group['group'] += second_group['group']
        first_group['length'] += second_group['length']
        lat, lon = get_group_centroid(first_group['group'])
        if lat is not None and lon is not None:
          first_group['centroid'] = (lat, lon)

    merged_groups.append(first_group['group'])
  return large_groups + merged_groups


def get_group_centroid(schedule_items):
  coords = []
  for item in schedule_items:
    lat, lon = get_lat_lon_by_cap(item['cap'])
    if lat is not None and lon is not None:
      coords.append((lat, lon))

  if not coords:
    return None, None

  return sum(lat for lat, lon in coords) / len(coords), sum(lon for lat, lon in coords) / len(coords)


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

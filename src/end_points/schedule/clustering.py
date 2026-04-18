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


# Maximum number of professional orders allowed per schedule group
MAX_PROFESSIONAL_ORDERS = 2


def _is_professional_order(item: ScheduleItem) -> bool:
  """Return True if the order has at least one product with a professional service."""
  for product in item.get('products', {}).values():
    for service in product.get('services', []):
      if isinstance(service, dict) and service.get('professional'):
        return True
  return False


def _count_professional_orders(group: ScheduleItemGroup) -> int:
  """Count the number of professional orders in a group."""
  return sum(1 for item in group if item.get('operation_type') == 'Order' and _is_professional_order(item))


class ProfessionalServicesLimitRule(ClusteringRule):
  def apply(
    self,
    schedule_item_groups: list[ScheduleItemGroup],
    context: ClusteringContext,
  ) -> list[ScheduleItemGroup]:
    # Fast path: skip redistribution only when every group already satisfies
    # both the professional-order limit AND the min/max size constraints.
    # If Split left an unbalanced result (e.g. [12, 8] with min=9), the size
    # check will fail and we fall through to rebalance.
    def _order_count(g: ScheduleItemGroup) -> int:
      return sum(1 for item in g if item.get('operation_type') == 'Order')

    if all(
      _count_professional_orders(g) <= MAX_PROFESSIONAL_ORDERS
      and context.min_size_group <= _order_count(g) <= context.max_size_group
      for g in schedule_item_groups
    ):
      return schedule_item_groups

    # Gather all collection points globally (keyed by collection_point_id)
    all_cp = {
      item['collection_point_id']: item
      for g in schedule_item_groups
      for item in g
      if item.get('operation_type') == 'CollectionPoint'
    }

    # Separate all orders globally into professional and non-professional
    all_pro = [
      item
      for g in schedule_item_groups
      for item in g
      if item.get('operation_type') == 'Order' and _is_professional_order(item)
    ]
    all_non_pro = [
      item
      for g in schedule_item_groups
      for item in g
      if item.get('operation_type') == 'Order' and not _is_professional_order(item)
    ]

    n_groups = len(schedule_item_groups)
    max_pro_capacity = n_groups * MAX_PROFESSIONAL_ORDERS

    # Pro orders that fit across the existing groups; any surplus goes to extra groups
    main_pro = all_pro[:max_pro_capacity]
    overflow_pro = all_pro[max_pro_capacity:]

    # Compute balanced sizes for the main groups so that a skewed split
    # (e.g. [12, 8] for 20 orders with max=12) does not survive redistribution.
    main_total = len(main_pro) + len(all_non_pro)
    base = main_total // n_groups
    extra = main_total % n_groups
    group_sizes = [base + (1 if i < extra else 0) for i in range(n_groups)]

    pro_iter = iter(main_pro)
    non_pro_iter = iter(all_non_pro)
    new_groups = []

    for size in group_sizes:
      orders: list[ScheduleItem] = []
      for _ in range(min(MAX_PROFESSIONAL_ORDERS, size)):
        order = next(pro_iter, None)
        if order is None:
          break
        orders.append(order)
      while len(orders) < size:
        order = next(non_pro_iter, None)
        if order is None:
          break
        orders.append(order)
      cp_ids = {
        product.get('collection_point', {}).get('id') for o in orders for product in o.get('products', {}).values()
      }
      cp_items = [all_cp[cp_id] for cp_id in cp_ids if cp_id in all_cp]
      new_groups.append(cp_items + orders)

    # Overflow pro orders that cannot fit in the main groups become extra groups.
    # These may be smaller than min_size_group — that is acceptable.
    for i in range(0, len(overflow_pro), MAX_PROFESSIONAL_ORDERS):
      chunk = overflow_pro[i : i + MAX_PROFESSIONAL_ORDERS]
      cp_ids = {
        product.get('collection_point', {}).get('id') for o in chunk for product in o.get('products', {}).values()
      }
      cp_items = [all_cp[cp_id] for cp_id in cp_ids if cp_id in all_cp]
      new_groups.append(cp_items + chunk)

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

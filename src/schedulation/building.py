from typing import Any
from collections import defaultdict

from .clustering_rules import ScheduleItemGroup


class ScheduleItemGroupBuilder:
  def build(
    self,
    orders: list[dict[str, Any]],
  ) -> list[ScheduleItemGroup]:
    schedule_item_groups = []
    orders_with_caps = [order for order in orders if get_order_caps(order)]
    cap_groups = find_cap_groups(orders_with_caps)
    unmatched_orders = []
    for order in orders:
      if not get_order_caps(order):
        order_cap = order.get('cap')
        matched_group_index = find_matching_group_index(order_cap, cap_groups, orders_with_caps) if order_cap else None
        if matched_group_index is not None:
          orders_with_caps.append(order)
          cap_groups[matched_group_index].add(order_cap)
        else:
          unmatched_orders.append(order)

    for group in cap_groups:
      group_orders = [order for order in orders_with_caps if get_order_caps(order) & group or order['cap'] in group]
      schedule_item_groups.append(build_schedule_items(group_orders))

    if unmatched_orders:
      schedule_item_groups.append(build_schedule_items(unmatched_orders))
    return schedule_item_groups


def find_matching_group_index(
  order_cap: str,
  cap_groups: list[set],
  orders_with_caps: list[dict[str, Any]],
) -> int | None:
  all_caps_in_group = [
    group | {order['cap'] for order in orders_with_caps if get_order_caps(order) & group} for group in cap_groups
  ]
  for index, caps in enumerate(all_caps_in_group):
    if order_cap in caps:
      return index

  return None


def build_schedule_items(orders):
  schedule_orders = []
  collection_point_ids = []
  schedule_collection_points = []
  for order in orders:
    schedule_orders.append(build_schedule_item(order, 'Order'))
    for product in order['products'].values():
      if 'collection_point' not in product or not product['collection_point']:
        continue

      if product['collection_point']['id'] not in collection_point_ids:
        schedule_collection_points.append(build_schedule_item(product['collection_point'], 'CollectionPoint'))
        collection_point_ids.append(product['collection_point']['id'])

  return [
    set_schedule_index(schedule_item, index)
    for (index, schedule_item) in enumerate(schedule_collection_points + schedule_orders)
  ]


def build_schedule_item(item, type):
  schedule_item = {
    'cap': item['cap'],
    'operation_type': type,
    'address': item['address'],
    ('order_id' if type == 'Order' else 'collection_point_id'): item['id'],
  }
  if type == 'Order':
    schedule_item['status'] = item['status']
    schedule_item['products'] = item['products']
    schedule_item['dpc'] = item['dpc']
    schedule_item['drc'] = item['drc']
    if 'booking_date' in item and item['booking_date']:
      schedule_item['booking_date'] = item['booking_date']
  return schedule_item


def set_schedule_index(item, index):
  new_item = item.copy()
  new_item['index'] = index
  return new_item


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
  return {product['collection_point']['cap'] for product in order['products'].values() if 'collection_point' in product}

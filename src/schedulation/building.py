from typing import Any
from collections import defaultdict

from .clustering_rules import ScheduleItemGroup


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


def build_schedule_items(orders):
  schedule_orders = []
  collection_point_ids = []
  schedule_collection_points = []
  for order in orders:
    schedule_orders.append(build_schedule_item(order, 'Order'))
    for product in order['products'].values():
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
  return {product['collection_point']['cap'] for product in order['products'].values()}

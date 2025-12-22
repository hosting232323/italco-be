from collections import defaultdict


def assign_orders_to_groups(orders):
  result = []
  for group in find_cap_groups(orders):
    group_orders = []
    for order in orders:
      order_caps = {product['collection_point']['cap'] for product in order['products'].values()}
      if order_caps & group:
        group_orders.append(order)
    result.append(build_schedule_items(group_orders))
  return result


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
    caps = {product['collection_point']['cap'] for product in order['products'].values()}
    for cap in caps:
      graph[cap].update(caps - {cap})
  return graph


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
  return schedule_collection_points + schedule_orders


def build_schedule_item(item, type):
  return {
    'cap': item['cap'],
    'operation_type': type,
    'address': item['address'],
    ('order_id' if type == 'Order' else 'collection_point_id'): item['id'],
  }

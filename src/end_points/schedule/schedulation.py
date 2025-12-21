from collections import defaultdict


def assign_orders_to_groups(orders):
  result = []
  for group in find_cap_groups(orders):
    group_orders = []
    for order in orders:
      order_caps = {p['collection_point']['cap'] for p in order['products'].values()}
      if order_caps & group:
        group_orders.append(order)
    result.append({'caps': list(group), 'orders': group_orders})
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

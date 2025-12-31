from geopy.distance import geodesic
from collections import defaultdict

from ..geographic_zone import CAPS_DATA


# QUESTO NON VA TROPPO BENE PERCHé L'ORDINE DEI GRUPPI DI ORDINI IMPATTA SUL RISULTATO


def assign_orders_to_groups(orders, delivery_users):
  available_delivery_users = [
    delivery_user
    for delivery_user in delivery_users
    if 'delivery_user_info' in delivery_user and 'cap' in delivery_user['delivery_user_info']
  ]

  result = []
  for group in find_cap_groups(orders):
    group_orders = []
    for order in orders:
      order_caps = {product['collection_point']['cap'] for product in order['products'].values()}
      if order_caps & group:
        group_orders.append(order)

    schedule_items = build_schedule_items(group_orders)
    if len(available_delivery_users) > 1:
      delivery_users = [assign_delivery_user(schedule_items, available_delivery_users)]
      available_delivery_users.remove(delivery_users[0])
    elif len(available_delivery_users) == 1:
      delivery_users = available_delivery_users.copy()
      available_delivery_users.remove(delivery_users[0])
    else:
      delivery_users = []

    result.append({'schedule_items': schedule_items, 'delivery_users': delivery_users})
  return result


def assign_delivery_user(schedule_items, delivery_users):
  return min(
    delivery_users,
    key=lambda delivery_user: sum(
      geodesic(
        get_lat_lon_by_cap(schedule_item['cap']), get_lat_lon_by_cap(delivery_user['delivery_user_info']['cap'])
      ).meters
      for schedule_item in schedule_items
    ),
  )


def get_lat_lon_by_cap(cap):
  for province in CAPS_DATA.keys():
    if cap in CAPS_DATA[province]:
      cap_data = CAPS_DATA[province][cap]
      return cap_data['lat'], cap_data['lon']


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
    schedule_item['products'] = item['products']
  return schedule_item


def set_schedule_index(item, index):
  item['index'] = index
  return item

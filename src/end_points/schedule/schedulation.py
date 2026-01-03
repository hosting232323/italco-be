from collections import defaultdict
from geopy.distance import geodesic
from scipy.optimize import linear_sum_assignment

from ..geographic_zone import CAPS_DATA


def assign_orders_to_groups(orders, delivery_users):
  schedule_item_groups = []
  for group in find_cap_groups(orders):
    group_orders = []
    for order in orders:
      order_caps = {product['collection_point']['cap'] for product in order['products'].values()}
      if order_caps & group:
        group_orders.append(order)
    schedule_item_groups.append(build_schedule_items(group_orders))

  available_delivery_users = [
    delivery_user
    for delivery_user in delivery_users
    if 'delivery_user_info' in delivery_user and 'cap' in delivery_user['delivery_user_info']
  ]
  if not available_delivery_users:
    return [
      {'schedule_items': schedule_item_group, 'delivery_users': []} for schedule_item_group in schedule_item_groups
    ]

  cost_matrix = []
  for user in available_delivery_users:
    user_costs = []
    for schedule_items in schedule_item_groups:
      user_costs.append(calculate_group_cost(user, schedule_items))
    cost_matrix.append(user_costs)

  delivery_user_indices, group_indices = linear_sum_assignment(cost_matrix)
  return [
    {
      'schedule_items': schedule_item_group,
      'delivery_users': [
        available_delivery_users[delivery_user_indices[user_index]]
        for user_index, group_index in enumerate(group_indices)
        if group_index == index
      ],
    }
    for index, schedule_item_group in enumerate(schedule_item_groups)
  ]


def calculate_group_cost(user, schedule_items):
  user_coord = get_lat_lon_by_cap(user['delivery_user_info']['cap'])
  return sum(geodesic(get_lat_lon_by_cap(item['cap']), user_coord).meters for item in schedule_items)


def get_lat_lon_by_cap(cap):
  for province in CAPS_DATA.keys():
    if cap in CAPS_DATA[province]:
      cap_data = CAPS_DATA[province][cap]
      return cap_data['lat'], cap_data['lon']

  raise ValueError('Cap not found')


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

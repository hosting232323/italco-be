from geopy.distance import geodesic
from scipy.optimize import linear_sum_assignment

from ...utils.caps import get_lat_lon_by_cap
from .clustering import ClusteringContext, ScheduleClusteringPipeline
from .experiments import set_schedule_index


def assign_orders_to_groups(orders, delivery_users, min_size_group, max_size_group, max_distance_km):
  schedule_item_groups = build_clustered_schedule_item_groups(
    orders,
    min_size_group,
    max_size_group,
    max_distance_km,
  )

  available_delivery_users = [
    delivery_user
    for delivery_user in delivery_users
    if 'delivery_user_info' in delivery_user and 'cap' in delivery_user['delivery_user_info']
  ]
  if not available_delivery_users:
    return [
      {'schedule_items': schedule_item_group, 'delivery_users': [], 'transports': []}
      for schedule_item_group in schedule_item_groups
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
      'transports': [],
      'schedule_items': schedule_item_group,
      'delivery_users': [
        available_delivery_users[delivery_user_indices[user_index]]
        for user_index, group_index in enumerate(group_indices)
        if group_index == index
      ],
    }
    for index, schedule_item_group in enumerate(schedule_item_groups)
  ]


def build_clustered_schedule_item_groups(orders, min_size_group, max_size_group, max_distance_km):
  clustering_pipeline = ScheduleClusteringPipeline()
  return clustering_pipeline.cluster(
    orders,
    build_schedule_items=build_schedule_items,
    context=ClusteringContext(
      min_size_group=min_size_group,
      max_size_group=max_size_group,
      max_distance_km=max_distance_km,
    ),
  )


def calculate_group_cost(user, schedule_items):
  user_coord = get_lat_lon_by_cap(user['delivery_user_info']['cap'])
  return sum(geodesic(get_lat_lon_by_cap(item['cap']), user_coord).meters for item in schedule_items)


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

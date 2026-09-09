from geopy.distance import geodesic
from scipy.optimize import linear_sum_assignment

from ..utils.caps import get_lat_lon_by_cap


def assign_delivery_users_to_schedule_items(schedule_item_groups, delivery_users, transports=None):
  available_delivery_users = [
    delivery_user
    for delivery_user in delivery_users
    if 'delivery_user_info' in delivery_user and 'cap' in delivery_user['delivery_user_info']
  ]
  if not available_delivery_users:
    groups = [
      {'schedule_items': schedule_item_group, 'delivery_users': [], 'transports': []}
      for schedule_item_group in schedule_item_groups
    ]
    return assign_transports_to_groups(groups, transports)

  cost_matrix = []
  for user in available_delivery_users:
    user_costs = []
    for schedule_items in schedule_item_groups:
      user_costs.append(calculate_group_cost(user, schedule_items))
    cost_matrix.append(user_costs)

  delivery_user_indices, group_indices = linear_sum_assignment(cost_matrix)
  groups = [
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
  return assign_transports_to_groups(groups, transports)


def assign_transports_to_groups(groups, transports):
  available_transports = [transport for transport in (transports or []) if transport.get('cap')]
  if not available_transports or not groups:
    return groups

  cost_matrix = []
  for transport in available_transports:
    transport_costs = []
    for group in groups:
      transport_costs.append(calculate_cap_cost(transport['cap'], group['schedule_items']))
    cost_matrix.append(transport_costs)

  transport_indices, group_indices = linear_sum_assignment(cost_matrix)
  for transport_index, group_index in zip(transport_indices, group_indices):
    groups[group_index]['transports'] = [available_transports[transport_index]]
  return groups


def calculate_group_cost(user, schedule_items):
  return calculate_cap_cost(user['delivery_user_info']['cap'], schedule_items)


def calculate_cap_cost(cap, schedule_items):
  origin_coord = get_lat_lon_by_cap(cap)
  return sum(geodesic(get_lat_lon_by_cap(item['cap']), origin_coord).meters for item in schedule_items)

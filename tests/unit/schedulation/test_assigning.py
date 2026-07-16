from src.schedulation.assigning import assign_delivery_users_to_schedule_items, calculate_group_cost

from tests.unit.schedulation.conftest import order_ids


def _schedule_item(cap):
  return {'operation_type': 'Order', 'order_id': int(cap[-2:]), 'cap': cap}


def test_calculate_group_cost_sums_distances():
  user = {'delivery_user_info': {'cap': '70121'}}
  items = [{'cap': '70121'}, {'cap': '70122'}]

  cost = calculate_group_cost(user, items)

  assert cost >= 0


def test_assign_returns_empty_users_without_delivery_info():
  groups = [[_schedule_item('70121')]]

  result = assign_delivery_users_to_schedule_items(groups, [{'id': 1}])

  assert result[0]['delivery_users'] == []
  assert result[0]['transports'] == []
  assert result[0]['schedule_items'] == groups[0]


def test_assign_matches_closest_delivery_user():
  groups = [[_schedule_item('70121')], [_schedule_item('71010')]]
  delivery_users = [
    {'id': 11, 'delivery_user_info': {'cap': '70122'}},
    {'id': 22, 'delivery_user_info': {'cap': '71011'}},
  ]

  result = assign_delivery_users_to_schedule_items(groups, delivery_users)

  assignment = {
    tuple(order_ids(group['schedule_items'])): [user['id'] for user in group['delivery_users']]
    for group in result
  }
  assert assignment == {(21,): [11], (10,): [22]}
  assert all(group['transports'] == [] for group in result)


def test_assign_ignores_users_without_cap():
  groups = [[_schedule_item('70121')]]
  delivery_users = [{'id': 1, 'delivery_user_info': {}}]

  result = assign_delivery_users_to_schedule_items(groups, delivery_users)

  assert result[0]['delivery_users'] == []

from src.schedulation.assigning import assign_transports_to_schedule_items, calculate_group_cost

from tests.unit.schedulation.conftest import order_ids


def _schedule_item(cap):
  return {'operation_type': 'Order', 'order_id': int(cap[-2:]), 'cap': cap}


def test_calculate_group_cost_sums_distances():
  transport = {'cap': '70121'}
  items = [{'cap': '70121'}, {'cap': '70122'}]

  cost = calculate_group_cost(transport, items)

  assert cost >= 0


def test_assign_returns_empty_transports_without_cap():
  groups = [[_schedule_item('70121')]]

  result = assign_transports_to_schedule_items(groups, [{'id': 1}])

  assert result[0]['transports'] == []
  assert result[0]['schedule_items'] == groups[0]


def test_assign_matches_closest_transport():
  groups = [[_schedule_item('70121')], [_schedule_item('71010')]]
  transports = [
    {'id': 11, 'cap': '70122'},
    {'id': 22, 'cap': '71011'},
  ]

  result = assign_transports_to_schedule_items(groups, transports)

  assignment = {
    tuple(order_ids(group['schedule_items'])): [transport['id'] for transport in group['transports']]
    for group in result
  }
  assert assignment == {(21,): [11], (10,): [22]}


def test_assign_ignores_transports_without_cap():
  groups = [[_schedule_item('70121')]]
  transports = [{'id': 1, 'cap': None}]

  result = assign_transports_to_schedule_items(groups, transports)

  assert result[0]['transports'] == []

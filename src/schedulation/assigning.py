from geopy.distance import geodesic
from scipy.optimize import linear_sum_assignment

from ..utils.caps import get_lat_lon_by_cap


def assign_transports_to_schedule_items(schedule_item_groups, transports):
  """Accoppia ogni gruppo di tappe al veicolo più vicino.

  L'accoppiamento è sul veicolo, non sul corriere: gli utenti delivery stanno
  sul veicolo e il borderò li eredita da lì, quindi è la località del veicolo
  a dire quale gruppo gli costa meno.
  """
  available_transports = [transport for transport in transports if transport.get('cap')]
  if not available_transports:
    return [{'schedule_items': schedule_item_group, 'transports': []} for schedule_item_group in schedule_item_groups]

  cost_matrix = []
  for transport in available_transports:
    transport_costs = []
    for schedule_items in schedule_item_groups:
      transport_costs.append(calculate_group_cost(transport, schedule_items))
    cost_matrix.append(transport_costs)

  transport_indices, group_indices = linear_sum_assignment(cost_matrix)
  return [
    {
      'schedule_items': schedule_item_group,
      'transports': [
        available_transports[transport_indices[transport_index]]
        for transport_index, group_index in enumerate(group_indices)
        if group_index == index
      ],
    }
    for index, schedule_item_group in enumerate(schedule_item_groups)
  ]


def calculate_group_cost(transport, schedule_items):
  transport_coord = get_lat_lon_by_cap(transport['cap'])
  if transport_coord[0] is None:
    return 0

  item_coords = (get_lat_lon_by_cap(item['cap']) for item in schedule_items)
  return sum(geodesic(coord, transport_coord).meters for coord in item_coords if coord[0] is not None)

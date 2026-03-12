from geopy.distance import geodesic

from ...utils.caps import get_lat_lon_by_cap


def split_large_groups(schedule_item_groups, min_size_group, max_size_group, max_distance_km):
  result = []
  for group in schedule_item_groups:
    order_items = [item for item in group if item['operation_type'] == 'Order']
    if len(order_items) <= max_size_group:
      result.append(group)
      continue

    collection_point_items = [item for item in group if item['operation_type'] == 'CollectionPoint']
    sub_groups = cluster_orders_by_cap(order_items, collection_point_items, max_size_group, max_distance_km)

    # After splitting, merge any sub-groups that are below min_size_group
    sub_groups = merge_small_sub_groups(sub_groups, min_size_group, max_size_group)
    result.extend(sub_groups)

  return enforce_max_size(result, max_size_group)


def merge_small_sub_groups(sub_groups, min_size_group, max_size_group):
  """After splitting, merge sub-groups below min_size_group into the nearest one."""
  if len(sub_groups) <= 1:
    return sub_groups

  def order_count(group):
    return len([item for item in group if item['operation_type'] == 'Order'])

  def group_centroid(group):
    coords = [get_lat_lon_by_cap(item['cap']) for item in group]
    coords = [(lat, lon) for lat, lon in coords if lat is not None and lon is not None]
    if not coords:
      return None
    return (sum(c[0] for c in coords) / len(coords), sum(c[1] for c in coords) / len(coords))

  changed = True
  while changed:
    changed = False
    small_index = next((i for i, g in enumerate(sub_groups) if order_count(g) < min_size_group), None)
    if small_index is None:
      break

    small_group = sub_groups[small_index]
    small_centroid = group_centroid(small_group)

    # First pass: find nearest candidate that respects max_size_group
    best_index = None
    best_dist = float('inf')
    for i, candidate in enumerate(sub_groups):
      if i == small_index:
        continue
      if order_count(candidate) + order_count(small_group) > max_size_group:
        continue
      candidate_centroid = group_centroid(candidate)
      if small_centroid and candidate_centroid:
        dist = geodesic(small_centroid, candidate_centroid).kilometers
      else:
        dist = float('inf')
      if dist < best_dist:
        best_dist = dist
        best_index = i

    if best_index is None:
      break

    existing_cp_ids = {
      item.get('collection_point_id') for item in sub_groups[best_index] if item['operation_type'] == 'CollectionPoint'
    }

    items_to_add = [
      item
      for item in small_group
      if item['operation_type'] == 'Order' or item.get('collection_point_id') not in existing_cp_ids
    ]

    merged = sub_groups[best_index] + items_to_add
    merged = [set_schedule_index(item, idx) for idx, item in enumerate(merged)]

    sub_groups[best_index] = merged
    sub_groups.pop(small_index)

    changed = True

  return sub_groups


def cluster_orders_by_cap(order_items, collection_point_items, max_size_group, max_distance_km):
  def get_coord(item):
    lat, lon = get_lat_lon_by_cap(item['cap'])
    return (lat, lon) if lat is not None and lon is not None else None

  valid_orders = []
  invalid_orders = []
  for item in order_items:
    coord = get_coord(item)
    if coord is not None:
      valid_orders.append((item, coord))
    else:
      invalid_orders.append(item)

  # Se nessun ordine ha coordinate, fallback: split sequenziale per count
  if not valid_orders:
    return split_sequentially(order_items, collection_point_items, max_size_group)

  valid_orders.sort(key=lambda x: x[1])

  assigned = [False] * len(valid_orders)
  sub_groups_orders = []

  while True:
    seed_index = next((i for i, a in enumerate(assigned) if not a), None)
    if seed_index is None:
      break

    assigned[seed_index] = True
    current_indices = [seed_index]
    centroid = valid_orders[seed_index][1]

    while len(current_indices) < max_size_group:
      best_index = None
      best_dist = float('inf')

      for i, (item, coord) in enumerate(valid_orders):
        if assigned[i]:
          continue
        dist = geodesic(centroid, coord).kilometers
        if dist <= max_distance_km and dist < best_dist:
          best_dist = dist
          best_index = i

      if best_index is None:
        break

      assigned[best_index] = True
      current_indices.append(best_index)

      coords = [valid_orders[i][1] for i in current_indices]
      centroid = (
        sum(c[0] for c in coords) / len(coords),
        sum(c[1] for c in coords) / len(coords),
      )

    sub_groups_orders.append([valid_orders[i][0] for i in current_indices])

  # Ordini senza coordinate: aggiunti all'ultimo sotto-gruppo o nuovo gruppo
  if invalid_orders:
    for order in invalid_orders:
      placed = False
      for group in sub_groups_orders:
        if len(group) < max_size_group:
          group.append(order)
          placed = True
          break
      if not placed:
        sub_groups_orders.append([order])

  # Se dopo il clustering un sotto-gruppo supera ancora max_size_group
  # (può succedere se invalid_orders lo ha ingrossato), lo risplittiamo sequenzialmente
  final_sub_groups_orders = []
  for orders_subset in sub_groups_orders:
    if len(orders_subset) > max_size_group:
      for i in range(0, len(orders_subset), max_size_group):
        final_sub_groups_orders.append(orders_subset[i : i + max_size_group])
    else:
      final_sub_groups_orders.append(orders_subset)

  return build_sub_groups(final_sub_groups_orders, collection_point_items)


def split_sequentially(order_items, collection_point_items, max_size_group):
  sub_groups_orders = [order_items[i : i + max_size_group] for i in range(0, len(order_items), max_size_group)]
  return build_sub_groups(sub_groups_orders, collection_point_items)


def build_sub_groups(sub_groups_orders, collection_point_items):
  result = []
  for orders_subset in sub_groups_orders:
    needed_cp_ids = set()
    for order in orders_subset:
      if 'products' in order:
        for product in order['products'].values():
          needed_cp_ids.add(product['collection_point']['id'])

    relevant_cps = [cp for cp in collection_point_items if cp.get('collection_point_id') in needed_cp_ids]

    sub_group = [set_schedule_index(item, idx) for idx, item in enumerate(relevant_cps + orders_subset)]
    result.append(sub_group)

  return result


def set_schedule_index(item, index):
  new_item = item.copy()
  new_item['index'] = index
  return new_item


def enforce_max_size(groups, max_size_group):
  result = []

  for group in groups:
    orders = [i for i in group if i['operation_type'] == 'Order']

    if len(orders) <= max_size_group:
      result.append(group)
      continue

    collection_points = [i for i in group if i['operation_type'] == 'CollectionPoint']

    for i in range(0, len(orders), max_size_group):
      chunk = orders[i : i + max_size_group]

      needed_cp_ids = set()

      for order in chunk:
        for product in order['products'].values():
          needed_cp_ids.add(product['collection_point']['id'])

      cps = [cp for cp in collection_points if cp.get('collection_point_id') in needed_cp_ids]

      new_group = [set_schedule_index(item, idx) for idx, item in enumerate(cps + chunk)]

      result.append(new_group)

  return result

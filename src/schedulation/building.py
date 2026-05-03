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
    schedule_item['status'] = item['status']
    schedule_item['products'] = item['products']
    schedule_item['dpc'] = item['dpc']
    schedule_item['drc'] = item['drc']
    if 'booking_date' in item and item['booking_date']:
      schedule_item['booking_date'] = item['booking_date']
  return schedule_item


def set_schedule_index(item, index):
  new_item = item.copy()
  new_item['index'] = index
  return new_item

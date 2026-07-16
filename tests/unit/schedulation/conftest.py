"""Helper condivisi per i test della pipeline di schedulazione.

I test di clustering lavorano su dizionari (non entità DB), quindi non
dipendono dal database: costruiscono ordini fittizi con CAP reali.
"""


def make_order(order_id, cap, collection_point_id=None, services=None, address=None):
  collection_point_id = collection_point_id if collection_point_id is not None else order_id
  return {
    'id': order_id,
    'cap': cap,
    'address': address or f'Order {order_id}',
    'status': 'Booked',
    'dpc': None,
    'drc': None,
    'products': {
      f'product-{order_id}': {
        'collection_point': {
          'id': collection_point_id,
          'cap': cap,
          'address': f'Collection point {collection_point_id}',
        },
        'services': services or [],
      }
    },
  }


def order_ids(group):
  return [item['order_id'] for item in group if item['operation_type'] == 'Order']


def count_orders(group):
  return sum(1 for item in group if item['operation_type'] == 'Order')


def count_professional(group):
  total = 0
  for item in group:
    if item['operation_type'] != 'Order':
      continue
    if any(
      isinstance(service, dict) and service.get('professional')
      for product in item.get('products', {}).values()
      for service in product.get('services', [])
    ):
      total += 1
  return total

"""Helper condivisi per i test della pipeline di schedulazione.

I test di clustering lavorano su dizionari (non entità DB), quindi non
dipendono dal database: costruiscono ordini fittizi con CAP reali.

La geocodifica dei CAP passa ora da Nominatim (chiamata di rete), quindi
qui la sostituiamo con coordinate fisse note per i CAP usati nei test,
per tenere la suite deterministica e senza dipendenze di rete.
"""

import pytest

# Coordinate reali (già verificate) per i CAP usati nei test di clustering.
_CAP_COORDINATES = {
  '70020': (40.9735386, 16.6173415),
  '70056': (41.1766334, 16.5701927),
  '70121': (41.1201889, 16.8753662),
  '70122': (41.1239663, 16.8665147),
  '70123': (41.1218456, 16.8561884),
  '70124': (41.0913466, 16.8473377),
  '70125': (41.0938196, 16.879792),
  '70126': (41.0985084, 16.9299579),
  '71010': (41.8128435, 15.1726816),
  '71011': (41.7908288, 15.4771084),
}


def _fake_get_lat_lon_by_cap(cap):
  return _CAP_COORDINATES.get(cap, (None, None))


def _fake_get_lat_lon_by_caps(caps):
  return [_fake_get_lat_lon_by_cap(cap) for cap in caps]


@pytest.fixture(autouse=True)
def stub_cap_geocoding(monkeypatch):
  import src.schedulation.assigning as assigning_module
  import src.schedulation.clustering_rules.merge_small_group as merge_module
  import src.schedulation.clustering_rules.split_large_group as split_module

  monkeypatch.setattr(assigning_module, 'get_lat_lon_by_cap', _fake_get_lat_lon_by_cap)
  monkeypatch.setattr(assigning_module, 'get_lat_lon_by_caps', _fake_get_lat_lon_by_caps)
  monkeypatch.setattr(merge_module, 'get_lat_lon_by_caps', _fake_get_lat_lon_by_caps)
  monkeypatch.setattr(split_module, 'get_lat_lon_by_caps', _fake_get_lat_lon_by_caps)


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

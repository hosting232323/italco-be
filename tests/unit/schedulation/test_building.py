from src.schedulation.building import (
  ScheduleItemGroupBuilder,
  build_schedule_items,
  find_cap_groups,
  get_order_caps,
  set_schedule_index,
)

from tests.unit.schedulation.conftest import make_order


def test_build_schedule_items_prepends_collection_points():
  items = build_schedule_items([make_order(1, '70121', collection_point_id=10)])

  operation_types = [item['operation_type'] for item in items]
  assert operation_types == ['CollectionPoint', 'Order']
  # Gli indici sono progressivi
  assert [item['index'] for item in items] == [0, 1]


def test_build_schedule_items_deduplicates_collection_points():
  orders = [
    make_order(1, '70121', collection_point_id=10),
    make_order(2, '70121', collection_point_id=10),
  ]

  items = build_schedule_items(orders)

  cp_items = [item for item in items if item['operation_type'] == 'CollectionPoint']
  assert len(cp_items) == 1


def test_build_schedule_items_keeps_stored_coordinates():
  order = make_order(1, '70122', collection_point_id=10)
  order['address_lat'], order['address_lon'] = 41.1276667, 16.8639301
  order['products']['product-1']['collection_point'].update({'lat': 41.098, 'lon': 16.93})

  collection_point, order_item = build_schedule_items([order])

  assert (order_item['address_lat'], order_item['address_lon']) == (41.1276667, 16.8639301)
  assert (collection_point['lat'], collection_point['lon']) == (41.098, 16.93)


def test_build_schedule_items_without_coordinates_omits_them():
  collection_point, order_item = build_schedule_items([make_order(1, '70122', collection_point_id=10)])

  assert 'address_lat' not in order_item and 'address_lon' not in order_item
  assert 'lat' not in collection_point and 'lon' not in collection_point


def test_get_order_caps_reads_collection_point_caps():
  order = make_order(1, '70121', collection_point_id=5)

  assert get_order_caps(order) == {'70121'}


def test_find_cap_groups_connects_shared_caps():
  orders = [
    make_order(1, '70121'),
    make_order(2, '70121'),
    make_order(3, '70056'),
  ]

  groups = find_cap_groups(orders)

  assert {frozenset(group) for group in groups} == {frozenset({'70121'}), frozenset({'70056'})}


def test_set_schedule_index_is_pure():
  item = {'operation_type': 'Order'}

  indexed = set_schedule_index(item, 3)

  assert indexed['index'] == 3
  assert 'index' not in item  # l'originale non viene mutato


def test_builder_groups_orders_by_cap_cluster():
  builder = ScheduleItemGroupBuilder()

  groups = builder.build(
    [
      make_order(1, '70121', collection_point_id=1),
      make_order(2, '70121', collection_point_id=1),
      make_order(3, '70056', collection_point_id=2),
    ]
  )

  order_counts = sorted(sum(1 for item in group if item['operation_type'] == 'Order') for group in groups)
  assert order_counts == [1, 2]


def test_builder_places_orders_without_caps_in_unmatched_group():
  order_without_cp = {
    'id': 9,
    'cap': '99999',
    'address': 'Senza CP',
    'status': 'Booked',
    'dpc': None,
    'drc': None,
    'products': {'p': {'services': []}},
  }

  groups = ScheduleItemGroupBuilder().build([order_without_cp])

  assert len(groups) == 1
  assert any(item['operation_type'] == 'Order' for item in groups[0])

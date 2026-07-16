from datetime import date

from database_api.operations import create

from src.database.enum import OrderStatus, UserRole
from src.database.schema import CustomerGroup, History
from src.end_points.orders.queries import (
  format_query_result,
  get_all_histories_by_order_id,
  get_delivery_user,
  get_motivations_by_order_id,
  get_order_by_external_id,
  get_order_by_external_id_and_customer,
  get_order_photos,
  get_selling_point,
  query_orders,
  query_products,
  query_service_users,
)

from tests.unit.factories import (
  create_delivery_group,
  create_order,
  create_product,
  create_schedule,
  create_user,
  customer_with_service,
  link_order_to_schedule,
)


def _orders_from(tuples):
  orders = []
  for tupla in tuples:
    orders = format_query_result(tupla, orders)
  return orders


def test_query_orders_empty_filters_returns_joined_rows(db):
  _, _, service_user, _ = customer_with_service()
  order = create_order()
  create_product(order, service_user)

  results = query_orders([])

  assert len(results) == 1
  assert results[0][0].id == order.id


def test_query_orders_work_date_single_value_matches_dpc_or_booking(db):
  _, _, service_user, _ = customer_with_service()
  target = create_order(dpc=date(2026, 7, 20))
  create_product(target, service_user)
  other = create_order(dpc=date(2026, 7, 1))
  create_product(other, service_user)

  results = query_orders([{'model': 'Order', 'field': 'work_date', 'value': '2026-07-20'}])

  assert [tupla[0].id for tupla in results] == [target.id]


def test_query_orders_work_date_range(db):
  _, _, service_user, _ = customer_with_service()
  inside = create_order(dpc=date(2026, 7, 20))
  create_product(inside, service_user)
  outside = create_order(dpc=date(2026, 8, 20))
  create_product(outside, service_user)

  results = query_orders(
    [{'model': 'Order', 'field': 'work_date', 'value': ['2026-07-15', '2026-07-25']}]
  )

  assert [tupla[0].id for tupla in results] == [inside.id]


def test_query_orders_date_range_filter_on_dpc(db):
  _, _, service_user, _ = customer_with_service()
  inside = create_order(dpc=date(2026, 7, 20))
  create_product(inside, service_user)
  outside = create_order(dpc=date(2026, 6, 1))
  create_product(outside, service_user)

  results = query_orders([{'model': 'Order', 'field': 'dpc', 'value': ['2026-07-19', '2026-07-21']}])

  assert [tupla[0].id for tupla in results] == [inside.id]


def test_query_orders_created_at_exact_date(db):
  _, _, service_user, _ = customer_with_service()
  order = create_order()
  create_product(order, service_user)

  results = query_orders(
    [{'model': 'Order', 'field': 'created_at', 'value': date.today().strftime('%Y-%m-%d')}]
  )

  assert [tupla[0].id for tupla in results] == [order.id]


def test_query_orders_addressee_is_case_insensitive_partial_match(db):
  _, _, service_user, _ = customer_with_service()
  order = create_order(addressee='Mario Rossi')
  create_product(order, service_user)
  other = create_order(addressee='Luigi Verdi')
  create_product(other, service_user)

  results = query_orders([{'model': 'Order', 'field': 'addressee', 'value': 'mario'}])

  assert [tupla[0].id for tupla in results] == [order.id]


def test_query_orders_id_list_filter(db):
  _, _, service_user, _ = customer_with_service()
  first = create_order()
  create_product(first, service_user)
  second = create_order()
  create_product(second, service_user)
  third = create_order()
  create_product(third, service_user)

  results = query_orders([{'model': 'Order', 'field': 'id', 'value': [first.id, second.id]}])

  assert {tupla[0].id for tupla in results} == {first.id, second.id}


def test_query_orders_delivery_user_filter(db):
  _, _, service_user, _ = customer_with_service()
  order = create_order()
  create_product(order, service_user)
  other_order = create_order()
  create_product(other_order, service_user)
  delivery = create_user(UserRole.DELIVERY)
  schedule = create_schedule()
  link_order_to_schedule(order, schedule)
  create_delivery_group(delivery, schedule)

  results = query_orders([{'model': 'DeliveryUser', 'field': 'id', 'value': delivery.id}])

  assert [tupla[0].id for tupla in results] == [order.id]


def test_query_orders_schedule_filter(db):
  _, _, service_user, _ = customer_with_service()
  order = create_order()
  create_product(order, service_user)
  schedule = create_schedule()
  link_order_to_schedule(order, schedule)

  results = query_orders([{'model': 'Schedule', 'field': 'id', 'value': schedule.id}])

  assert [tupla[0].id for tupla in results] == [order.id]


def test_query_orders_customer_group_filter(db):
  group = create(CustomerGroup, {'name': 'GDO'})
  customer, _, service_user, _ = customer_with_service()
  from database_api.operations import update

  update(customer, {'customer_group_id': group.id})
  order = create_order()
  create_product(order, service_user)

  results = query_orders([{'model': 'CustomerGroup', 'field': 'id', 'value': group.id}])

  assert [tupla[0].id for tupla in results] == [order.id]


def test_query_orders_respects_limit_per_order(db):
  _, _, service_user, _ = customer_with_service()
  for _ in range(3):
    order = create_order()
    create_product(order, service_user)

  results = query_orders([], limit=2)

  assert len({tupla[0].id for tupla in results}) == 2


def test_format_query_result_aggregates_products_and_price(db):
  _, _, service_user, collection_point = customer_with_service(price=15.0)
  order = create_order()
  create_product(order, service_user, name='TV', collection_point_id=collection_point.id)
  create_product(order, service_user, name='Soundbar')

  orders = _orders_from(query_orders([]))

  assert len(orders) == 1
  assert orders[0]['price'] == 30.0
  assert set(orders[0]['products']) == {'TV', 'Soundbar'}
  assert orders[0]['products']['TV']['collection_point']['id'] == collection_point.id


def test_format_query_result_does_not_duplicate_services(db):
  _, _, service_user, _ = customer_with_service(price=7.0)
  order = create_order()
  create_product(order, service_user, name='TV')

  tuples = query_orders([]) * 2  # simula il fan-out del join
  orders = _orders_from(tuples)

  assert orders[0]['price'] == 7.0
  assert len(orders[0]['products']['TV']['services']) == 1


def test_query_products_returns_order_products(db):
  _, _, service_user, _ = customer_with_service()
  order = create_order()
  create_product(order, service_user, name='Frigo')

  products = query_products(order)

  assert [product.name for product in products] == ['Frigo']


def test_query_service_users_filters_by_type_and_user(db):
  customer, service, service_user, _ = customer_with_service()

  from src.database.enum import OrderType

  results = query_service_users([service.id], customer.id, OrderType.DELIVERY)
  wrong_type = query_service_users([service.id], customer.id, OrderType.WITHDRAW)

  assert [su.id for su in results] == [service_user.id]
  assert wrong_type == []


def test_get_order_photos_and_motivations(db):
  from src.database.schema import Motivation, Photo

  order = create_order()
  create(Photo, {'order_id': order.id, 'link': 'http://x/1.jpg'})
  create(Motivation, {'order_id': order.id, 'status': OrderStatus.NOT_DELIVERED, 'text': 'm'})

  assert [photo.link for photo in get_order_photos(order.id)] == ['http://x/1.jpg']
  assert [motivation.text for motivation in get_motivations_by_order_id(order.id)] == ['m']


def test_get_selling_point_returns_customer(db):
  customer, _, service_user, _ = customer_with_service()
  order = create_order()
  create_product(order, service_user)

  assert get_selling_point(order).id == customer.id


def test_get_delivery_user_returns_assigned_driver(db):
  _, _, service_user, _ = customer_with_service()
  order = create_order()
  create_product(order, service_user)
  delivery = create_user(UserRole.DELIVERY)
  schedule = create_schedule()
  link_order_to_schedule(order, schedule)
  create_delivery_group(delivery, schedule)

  assert get_delivery_user(order).id == delivery.id


def test_get_order_by_external_id_variants(db):
  customer, _, service_user, _ = customer_with_service()
  order = create_order(external_id='EXT-1')
  create_product(order, service_user)

  assert get_order_by_external_id('EXT-1').id == order.id
  assert get_order_by_external_id('EXT-MISSING') is None
  assert get_order_by_external_id_and_customer('EXT-1', customer.id).id == order.id
  assert get_order_by_external_id_and_customer('EXT-1', customer.id + 999) is None


def test_get_all_histories_by_order_id_is_ordered(db):
  from database_api.operations import update

  order = create_order(status=OrderStatus.ACQUIRED)
  update(order, {'status': OrderStatus.BOOKED})

  histories = get_all_histories_by_order_id(order.id)

  assert [h.status['value'] for h in histories if h.status['type'] == 'status'] == ['Acquired', 'Booked']
  assert all(isinstance(h, History) for h in histories)

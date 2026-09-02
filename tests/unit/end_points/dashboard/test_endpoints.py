from datetime import date

from src.database.enum import OrderStatus, OrderType, RaeStatus, UserRole

from tests.unit.factories import (
  auth_header,
  create_order,
  create_product,
  create_rae_product,
  create_rae_product_group,
  create_user,
  customer_with_service,
)


WEEKDAYS = ['Lun', 'Mar', 'Mer', 'Gio', 'Ven', 'Sab', 'Dom']


def _analytics(client, user, body=None):
  response = client.post('/dashboard/analytics', json=body or {}, headers=auth_header(user))
  return response, response.get_json()


def _weekday_count(rows, day: date) -> int:
  label = WEEKDAYS[day.isoweekday() - 1]
  return next(row['count'] for row in rows if row['label'] == label)


def _label_count(rows, label: str) -> int:
  return next((row['count'] for row in rows if row['label'] == label), 0)


def test_analytics_allowed_for_admin_and_operator(client):
  for role in (UserRole.ADMIN, UserRole.OPERATOR):
    response, body = _analytics(client, create_user(role))
    assert response.status_code == 200
    assert body['status'] == 'ok'
    assert set(body['analytics']) == {
      'kpis',
      'orders_by_status',
      'orders_by_weekday',
      'orders_over_time',
      'top_customers',
      'rae_by_status',
      'rae_by_group',
    }


def test_analytics_rejected_for_customer_and_delivery(client):
  # Un ruolo non abilitato non e' una sessione da rinnovare: e' un 403.
  for role in (UserRole.CUSTOMER, UserRole.DELIVERY):
    response, body = _analytics(client, create_user(role))
    assert response.status_code == 403
    assert body['status'] == 'forbidden'
    assert 'analytics' not in body


def test_kpis_counts(client):
  admin = create_user(UserRole.ADMIN)
  customer = create_user(UserRole.CUSTOMER)
  create_order(OrderStatus.DELIVERED)
  create_order(OrderStatus.DELIVERED)
  create_order(OrderStatus.NOT_DELIVERED)
  create_order(OrderStatus.ACQUIRED, anomaly=True)
  create_order(OrderStatus.SCHEDULED, delay=True)
  create_rae_product(create_order(OrderStatus.DELIVERED), customer)

  _, body = _analytics(client, admin)
  kpis = body['analytics']['kpis']

  assert kpis['total_orders'] == 6
  assert kpis['delivered_orders'] == 3
  assert kpis['not_delivered_orders'] == 1
  assert kpis['in_progress_orders'] == 2
  assert kpis['delivery_rate'] == 50.0
  assert kpis['anomaly_orders'] == 1
  assert kpis['delay_orders'] == 1
  assert kpis['rae_products'] == 1


def test_kpis_empty_database_has_zero_delivery_rate(client):
  _, body = _analytics(client, create_user(UserRole.ADMIN))
  assert body['analytics']['kpis'] == {
    'total_orders': 0,
    'delivered_orders': 0,
    'not_delivered_orders': 0,
    'in_progress_orders': 0,
    'delivery_rate': 0,
    'anomaly_orders': 0,
    'delay_orders': 0,
    'rae_products': 0,
  }


def test_orders_by_status(client):
  create_order(OrderStatus.DELIVERED)
  create_order(OrderStatus.DELIVERED)
  create_order(OrderStatus.ACQUIRED)

  _, body = _analytics(client, create_user(UserRole.ADMIN))
  rows = body['analytics']['orders_by_status']

  assert _label_count(rows, 'Delivered') == 2
  assert _label_count(rows, 'Acquired') == 1


def test_orders_by_weekday_uses_booking_then_dpc_fallback(client):
  monday = date(2026, 7, 27)
  wednesday = date(2026, 7, 29)
  create_order(booking_date=monday, dpc=wednesday)
  create_order(booking_date=None, dpc=wednesday)

  _, body = _analytics(client, create_user(UserRole.ADMIN))
  rows = body['analytics']['orders_by_weekday']

  assert len(rows) == 7
  assert [row['label'] for row in rows] == WEEKDAYS
  assert _weekday_count(rows, monday) == 1
  assert _weekday_count(rows, wednesday) == 1


def test_orders_over_time_groups_by_day(client):
  create_order(OrderStatus.DELIVERED)
  create_order(OrderStatus.ACQUIRED)

  _, body = _analytics(client, create_user(UserRole.ADMIN))
  rows = body['analytics']['orders_over_time']

  assert rows == [{'date': date.today().isoformat(), 'count': 2}]


def test_top_customers_ranked_by_distinct_orders(client):
  admin = create_user(UserRole.ADMIN)
  big_customer, _, big_service_user, _ = customer_with_service()
  small_customer, _, small_service_user, _ = customer_with_service()

  for _ in range(3):
    create_product(create_order(), big_service_user)
  create_product(create_order(), small_service_user)

  _, body = _analytics(client, admin)
  rows = body['analytics']['top_customers']

  assert rows[0] == {'label': big_customer.email, 'count': 3}
  assert rows[1] == {'label': small_customer.email, 'count': 1}


def test_top_customers_counts_each_order_once(client):
  admin = create_user(UserRole.ADMIN)
  customer, _, service_user, _ = customer_with_service()
  order = create_order()
  create_product(order, service_user, name='product-a')
  create_product(order, service_user, name='product-b')

  _, body = _analytics(client, admin)
  rows = body['analytics']['top_customers']

  assert rows == [{'label': customer.email, 'count': 1}]


def test_rae_grouped_by_status_and_group(client):
  admin = create_user(UserRole.ADMIN)
  customer = create_user(UserRole.CUSTOMER)
  group = create_rae_product_group(name='Lavatrici')
  create_rae_product(create_order(), customer, group=group, status=RaeStatus.EMITTED)
  create_rae_product(create_order(), customer, group=group, status=RaeStatus.EMITTED)
  create_rae_product(create_order(), customer, group=group, status=RaeStatus.LDR)

  _, body = _analytics(client, admin)

  assert _label_count(body['analytics']['rae_by_status'], 'Emitted') == 2
  assert _label_count(body['analytics']['rae_by_status'], 'LDR') == 1
  assert _label_count(body['analytics']['rae_by_group'], 'Lavatrici') == 3


def test_date_range_excludes_orders_out_of_window(client):
  create_order(OrderStatus.DELIVERED, order_type=OrderType.DELIVERY)

  _, body = _analytics(client, create_user(UserRole.ADMIN), {'start': '2000-01-01', 'end': '2000-12-31'})
  analytics = body['analytics']

  assert analytics['kpis']['total_orders'] == 0
  assert analytics['orders_by_status'] == []
  assert analytics['orders_over_time'] == []
  assert analytics['top_customers'] == []

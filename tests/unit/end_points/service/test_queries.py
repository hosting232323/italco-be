from datetime import date, timedelta

from src.database.enum import UserRole
from src.end_points.service.queries import (
  format_query_result,
  format_service_user,
  get_service_user_by_user_and_code,
  get_service_users,
  query_max_order,
  query_orders_in_range,
  query_service_user,
  query_services,
)

from tests.unit.factories import (
  create_order,
  create_product,
  create_service,
  create_service_user,
  create_user,
  customer_with_service,
)


def test_query_services_admin_includes_unassigned(db):
  admin = create_user(UserRole.ADMIN)
  create_service()

  results = query_services(admin)

  assert len(results) == 1
  assert results[0][1] is None and results[0][2] is None


def test_query_services_customer_only_own(db):
  customer = create_user(UserRole.CUSTOMER)
  own_service = create_service()
  create_service_user(customer, own_service)
  create_service()

  results = query_services(customer)

  assert [tupla[0].id for tupla in results] == [own_service.id]


def test_query_service_user_list_and_single(db):
  customer = create_user(UserRole.CUSTOMER)
  service = create_service()
  service_user = create_service_user(customer, service)

  all_links = query_service_user(service.id)
  single = query_service_user(service.id, customer.id)

  assert [link.id for link in all_links] == [service_user.id]
  assert single.id == service_user.id
  assert query_service_user(service.id, customer.id + 999) is None


def test_format_query_result_groups_duplicate_services(db):
  customer = create_user(UserRole.CUSTOMER)
  service = create_service()
  service_user = create_service_user(customer, service)

  results = []
  for tupla in [(service, service_user, customer)] * 2:
    results = format_query_result(tupla, results)

  assert len(results) == 1
  assert len(results[0]['users']) == 2  # il fan-out del join viene accodato per riga


def test_format_service_user_adds_email(db):
  customer = create_user(UserRole.CUSTOMER, email='pv-bari')
  service_user = create_service_user(customer, create_service())

  formatted = format_service_user(service_user, customer)

  assert formatted['email'] == 'pv-bari'
  assert formatted['id'] == service_user.id


def test_query_max_order_only_returns_bounded_services(db):
  bounded = create_service(max_services=3)
  create_service()  # senza max_services

  results = query_max_order([bounded.id])

  assert [service.id for service in results] == [bounded.id]


def test_query_orders_in_range_filters_by_service_and_date(db):
  customer, service, service_user, _ = customer_with_service()
  inside = create_order(dpc=date.today() + timedelta(days=1))
  create_product(inside, service_user)
  outside = create_order(dpc=date.today() + timedelta(days=90))
  create_product(outside, service_user)

  results = query_orders_in_range([service.id], date.today(), date.today() + timedelta(days=30))

  assert [order.id for order in results] == [inside.id]


def test_get_service_users_by_user(db):
  customer = create_user(UserRole.CUSTOMER)
  first = create_service_user(customer, create_service())
  second = create_service_user(customer, create_service())

  results = get_service_users(customer.id)

  assert {su.id for su in results} == {first.id, second.id}


def test_get_service_user_by_user_and_code(db):
  customer = create_user(UserRole.CUSTOMER)
  service_user = create_service_user(customer, create_service(), code='SVC-1')

  assert get_service_user_by_user_and_code(customer.id, 'SVC-1').id == service_user.id
  assert get_service_user_by_user_and_code(customer.id, 'SVC-MISSING') is None

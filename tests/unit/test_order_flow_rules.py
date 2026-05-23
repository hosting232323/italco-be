from datetime import date, datetime, timedelta
from types import SimpleNamespace

from database_api import Session
from database_api.operations import get_by_id

import src.end_points.customer_rule as customer_rule_endpoints
from src.database.enum import OrderStatus, UserRole
from src.database.schema import Order, ServiceUser
from src.end_points.orders.crud import update_order
from src.end_points.service.queries import query_service_user
from tests.unit.factories import create_acquired_order, create_test_service, create_test_service_user, create_test_user
from tests.utils import auth_header_for, create_user_for_login


def test_get_services_for_customer_returns_only_associated_services(client):
  customer_a = create_test_user('customer.visible', UserRole.CUSTOMER)
  customer_b = create_test_user('customer.hidden', UserRole.CUSTOMER)
  visible_service = create_test_service('Visible service')
  hidden_service = create_test_service('Hidden service')
  create_test_service_user(customer_a.id, visible_service.id, price=45.0, code='VIS-001')
  create_test_service_user(customer_b.id, hidden_service.id, price=55.0, code='HID-001')

  response = client.get('/service', headers=auth_header_for(customer_a.nickname, role=UserRole.CUSTOMER))

  assert response.status_code == 200
  body = response.get_json()
  assert body['status'] == 'ok'
  assert {service['id'] for service in body['services']} == {visible_service.id}
  assert {user['user_id'] for service in body['services'] for user in service['users']} == {customer_a.id}


def test_create_service_user_rejects_non_customer_user(client):
  service = create_test_service('Association guarded service')
  operator = create_test_user('operator.target', UserRole.OPERATOR)

  response = client.post(
    '/service/customer',
    json={'service_id': service.id, 'user_id': operator.id, 'price': 12.5},
    headers=auth_header_for('admin', role=UserRole.ADMIN),
  )

  assert response.status_code == 200
  body = response.get_json()
  assert body['status'] == 'ko'
  assert 'customer' in body['error'].lower()
  assert query_service_user(service.id, operator.id) is None


def test_update_service_user_rejects_non_customer_user(client):
  customer = create_test_user('customer.allowed', UserRole.CUSTOMER)
  delivery = create_test_user('delivery.blocked', UserRole.DELIVERY)
  service = create_test_service('Reassignment guarded service')
  service_user = create_test_service_user(customer.id, service.id, price=33.0, code='UPD-001')

  response = client.put(
    f'/service/customer/{service_user.id}',
    json={'user_id': delivery.id, 'price': 44.0},
    headers=auth_header_for('admin', role=UserRole.ADMIN),
  )

  assert response.status_code == 200
  body = response.get_json()
  assert body['status'] == 'ko'
  assert 'customer' in body['error'].lower()

  reloaded_service_user = get_by_id(ServiceUser, service_user.id)
  assert reloaded_service_user.user_id == customer.id
  assert reloaded_service_user.price == 33.0


def test_update_order_promotes_acquired_order_to_booked_when_booking_date_is_added(seeded_db):
  admin_user = create_user_for_login('admin', 'pw', UserRole.ADMIN)
  expected_booking_date = date.today() + timedelta(days=4)
  order = create_acquired_order()

  with Session() as session:
    persisted_order = get_by_id(Order, order.id, session=session)
    update_order(admin_user, persisted_order, {'booking_date': expected_booking_date}, session)
    session.commit()

  updated_order = get_by_id(Order, order.id)
  assert updated_order.status == OrderStatus.BOOKED
  assert updated_order.booking_date == expected_booking_date


def test_check_customer_rules_excludes_saturated_rule_day(monkeypatch):
  fixed_today = datetime(2026, 1, 5, 9, 0, 0)

  class FixedDateTime:
    @classmethod
    def today(cls):
      return fixed_today

  monkeypatch.setattr(customer_rule_endpoints, 'datetime', FixedDateTime)
  monkeypatch.setattr(
    customer_rule_endpoints,
    'query_my_customer_rules',
    lambda user: [SimpleNamespace(day_of_week=fixed_today.weekday(), max_orders=1)],
  )
  monkeypatch.setattr(
    customer_rule_endpoints,
    'query_my_orders',
    lambda user: [SimpleNamespace(dpc=fixed_today.date())],
  )

  allowed_dates = customer_rule_endpoints.check_customer_rules(SimpleNamespace(id=123))

  assert fixed_today.date().isoformat() not in allowed_dates
  assert (fixed_today.date() + timedelta(days=1)).isoformat() in allowed_dates

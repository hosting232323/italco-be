from datetime import date, timedelta

from database_api.operations import create, get_by_id

from src.database.enum import UserRole
from src.database.schema import CustomerRule
from src.end_points.customer_rule import check_customer_rules

from tests.unit.factories import (
  auth_header,
  create_order,
  create_product,
  create_user,
  customer_with_service,
)


def _rule(customer, day_of_week, max_orders=1):
  return create(CustomerRule, {'user_id': customer.id, 'day_of_week': day_of_week, 'max_orders': max_orders})


def test_create_customer_rule(client):
  admin = create_user(UserRole.ADMIN)
  customer = create_user(UserRole.CUSTOMER)

  response = client.post(
    '/customer-rule',
    json={'user_id': customer.id, 'day_of_week': 2, 'max_orders': 3},
    headers=auth_header(admin),
  )

  body = response.get_json()
  assert body['status'] == 'ok'
  assert body['customer_rules']['day_of_week'] == 2


def test_create_customer_rule_rejects_invalid_day(client):
  admin = create_user(UserRole.ADMIN)
  customer = create_user(UserRole.CUSTOMER)

  response = client.post(
    '/customer-rule',
    json={'user_id': customer.id, 'day_of_week': 7, 'max_orders': 3},
    headers=auth_header(admin),
  )

  # ValueError intercettata dall'handler globale
  assert response.get_json() == {'status': 'ko', 'message': 'Errore generico'}


def test_delete_customer_rules_bulk(client):
  admin = create_user(UserRole.ADMIN)
  customer = create_user(UserRole.CUSTOMER)
  first = _rule(customer, 0)
  second = _rule(customer, 1)

  response = client.delete(
    '/customer-rule', json={'ids': [first.id, second.id]}, headers=auth_header(admin)
  )

  assert response.get_json()['status'] == 'ok'
  assert get_by_id(CustomerRule, first.id) is None
  assert get_by_id(CustomerRule, second.id) is None


def test_get_customer_rules_grouped_by_user(client):
  admin = create_user(UserRole.ADMIN)
  customer = create_user(UserRole.CUSTOMER)
  _rule(customer, 0)
  _rule(customer, 1)

  response = client.get('/customer-rule', headers=auth_header(admin))

  body = response.get_json()
  assert body['status'] == 'ok'
  assert len(body['customer_rules']) == 1
  assert len(body['customer_rules'][0]['rules']) == 2


def test_check_customer_rules_allows_free_days(app, db):
  customer, _, _, _ = customer_with_service()

  with app.test_request_context():
    allowed = check_customer_rules(customer)

  # Nessuna regola: tutte le date dei prossimi 2 mesi sono permesse
  assert date.today().strftime('%Y-%m-%d') in allowed
  assert len(allowed) >= 60


def test_check_customer_rules_blocks_saturated_day(app, db):
  customer, _, service_user, _ = customer_with_service()
  target = date.today() + timedelta(days=7)
  _rule(customer, target.weekday(), max_orders=1)
  order = create_order(dpc=target)
  create_product(order, service_user)

  with app.test_request_context():
    allowed = check_customer_rules(customer)

  assert target.strftime('%Y-%m-%d') not in allowed


def test_check_customer_rules_allows_day_below_limit(app, db):
  customer, _, _, _ = customer_with_service()
  target = date.today() + timedelta(days=7)
  _rule(customer, target.weekday(), max_orders=2)

  with app.test_request_context():
    allowed = check_customer_rules(customer)

  assert target.strftime('%Y-%m-%d') in allowed

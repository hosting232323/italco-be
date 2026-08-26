"""Test delle route registrate direttamente sull'app (src/__init__.py, src/__main__.py)."""

import src.__main__ as main_module
from src.database.enum import UserRole

from tests.unit.factories import auth_header, create_user


def test_index_route(client):
  response = client.get('/')

  assert response.status_code == 200
  assert response.get_data(as_text=True) == 'Hello World'


def test_all_blueprints_are_registered(app):
  expected_prefixes = {
    '/log',
    '/rae',
    '/user',
    '/order',
    '/chatty',
    '/import',
    '/export',
    '/service',
    '/schedule',
    '/transport',
    '/customer-rule',
    '/customer-group',
    '/geographic-zone',
    '/collection-point',
  }
  registered = {rule.rule.split('/')[1] for rule in app.url_map.iter_rules() if rule.rule != '/'}

  assert {f'/{prefix}' for prefix in registered} >= expected_prefixes


def test_check_constraints_intersects_rule_sets(client, monkeypatch):
  customer = create_user(UserRole.CUSTOMER)
  monkeypatch.setattr(main_module, 'check_customer_rules', lambda user: ['2026-07-15', '2026-07-16', '2026-07-17'])
  monkeypatch.setattr(main_module, 'check_geographic_zone', lambda: ['2026-07-16', '2026-07-17', '2026-07-18'])
  monkeypatch.setattr(main_module, 'check_services_date', lambda: ['2026-07-16', '2026-07-17'])

  response = client.post('/check-constraints', json={}, headers=auth_header(customer))

  body = response.get_json()
  assert body['status'] == 'ok'
  assert body['dates'] == ['2026-07-16', '2026-07-17']


def test_check_constraints_requires_customer_role(client):
  admin = create_user(UserRole.ADMIN)

  response = client.post('/check-constraints', json={}, headers=auth_header(admin))

  assert response.status_code == 403
  assert response.get_json()['status'] == 'forbidden'


def test_checks_endpoint_without_swagger_key_is_denied(client, monkeypatch):
  response = client.get('/checks')

  # Senza SwaggerAuthorization valido lo swagger_decorator nega l'accesso
  assert response.get_json()['status'] == 'ko'

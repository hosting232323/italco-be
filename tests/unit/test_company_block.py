"""Blocco manuale di un'attività da parte del super admin."""

import pytest

from database_api.operations import get_by_id, update

from src.database.enum import UserRole
from src.database.schema import Company
from src.end_points.subscription import stripe_client

from tests.unit.factories import auth_header, create_super_admin, create_user
from tests.unit.test_subscription import stripe_subscription


@pytest.fixture
def admin(db):
  return create_user(UserRole.ADMIN)


@pytest.fixture
def blocked(db):
  return update(db, {'blocked': True, 'automatic_payment': True, 'subscription_price_cents': 4900})


def block(client, company, flag, super_admin=None):
  super_admin = super_admin or create_super_admin()
  return client.put(f'/company/{company.id}/block', json={'blocked': flag}, headers=auth_header(super_admin)).get_json()


def test_company_starts_unblocked(db):
  assert db.blocked is False


def test_super_admin_blocks_and_unblocks_a_company(db, client):
  super_admin = create_super_admin()

  assert block(client, db, True, super_admin)['company']['blocked'] is True
  assert get_by_id(Company, db.id).blocked is True
  assert block(client, db, False, super_admin)['company']['blocked'] is False


def test_block_needs_a_boolean_and_an_existing_company(db, client):
  headers = auth_header(create_super_admin())

  assert client.put(f'/company/{db.id}/block', json={'blocked': 'yes'}, headers=headers).get_json()['status'] == 'ko'
  assert client.put('/company/999999/block', json={'blocked': True}, headers=headers).get_json()['status'] == 'ko'


def test_admin_cannot_block(db, client, admin):
  response = client.put(f'/company/{db.id}/block', json={'blocked': True}, headers=auth_header(admin))

  assert response.status_code == 403


def test_blocked_company_users_are_refused(blocked, client, admin):
  body = client.get('/user', headers=auth_header(admin)).get_json()

  assert body['status'] == 'company_blocked'


def test_blocked_admin_can_still_read_his_company_and_the_subscription(blocked, client, admin):
  assert client.get('/company/me', headers=auth_header(admin)).get_json()['company']['blocked'] is True
  assert client.get('/subscription', headers=auth_header(admin)).get_json()['status'] == 'ok'


def test_any_role_can_reread_the_company_status_while_blocked(blocked, client):
  operator = create_user(UserRole.OPERATOR)

  body = client.get('/company/me/status', headers=auth_header(operator)).get_json()

  assert body['status'] == 'ok'
  assert body['company']['blocked'] is True
  update(blocked, {'blocked': False})
  assert client.get('/company/me/status', headers=auth_header(operator)).get_json()['company']['blocked'] is False


def test_super_admin_is_not_stopped_by_a_blocked_company(blocked, client):
  super_admin = create_super_admin()

  response = client.get('/user', headers=auth_header(super_admin, blocked.id))

  assert response.status_code == 200


def test_company_payload_reports_the_block(blocked):
  # È lo stesso dict che il login manda al frontend.
  assert blocked.to_dict()['blocked'] is True


def test_paying_unblocks_a_company_that_was_not_paying(blocked, client, admin, monkeypatch):
  monkeypatch.setattr(stripe_client, 'create_customer', lambda company_id, name: 'cus_1')
  monkeypatch.setattr(stripe_client, 'create_checkout_url', lambda *args: 'https://stripe.test/checkout')
  client.post('/subscription/checkout', headers=auth_header(admin))
  monkeypatch.setattr(stripe_client, 'list_subscriptions', lambda customer_id: [stripe_subscription(blocked.id)])

  client.post('/subscription/sync', headers=auth_header(admin))

  assert get_by_id(Company, blocked.id).blocked is False


def test_an_already_paying_company_stays_blocked_when_stripe_is_read_again(blocked, client, admin, monkeypatch):
  monkeypatch.setattr(stripe_client, 'create_customer', lambda company_id, name: 'cus_1')
  monkeypatch.setattr(stripe_client, 'create_checkout_url', lambda *args: 'https://stripe.test/checkout')
  client.post('/subscription/checkout', headers=auth_header(admin))
  monkeypatch.setattr(stripe_client, 'list_subscriptions', lambda customer_id: [stripe_subscription(blocked.id)])
  client.post('/subscription/sync', headers=auth_header(admin))

  block(client, blocked, True)
  client.post('/subscription/sync', headers=auth_header(admin))

  assert get_by_id(Company, blocked.id).blocked is True

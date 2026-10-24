"""Prezzo dell'abbonamento deciso dal super admin, anche con un abbonamento già attivo.

Stripe è sostituito: si verifica cosa gli viene chiesto e cosa resta salvato.
"""

from types import SimpleNamespace

import pytest

from database_api.operations import create, get_by_id, update

from src.database.enum import UserRole
from src.database.schema import Company, CompanySubscription
from src.end_points.subscription import get_subscription, stripe_client

from tests.unit.factories import auth_header, create_super_admin, create_user


@pytest.fixture
def super_admin(db):
  return create_super_admin()


@pytest.fixture
def active_subscription(db):
  update(db, {'automatic_payment': True, 'subscription_price_cents': 4900})
  return create(
    CompanySubscription,
    {'company_id': db.id, 'stripe_customer_id': 'cus_1', 'stripe_subscription_id': 'sub_1', 'status': 'active'},
  )


@pytest.fixture
def stripe_updates(monkeypatch):
  calls = []
  monkeypatch.setattr(stripe_client, 'update_subscription_price', lambda *args: calls.append(args))
  return calls


def stored_price(company):
  return get_by_id(Company, company.id).subscription_price_cents


def put_price(client, super_admin, company_id, **payload):
  return client.put(
    f'/subscription/company/{company_id}/price', json=payload, headers=auth_header(super_admin)
  ).get_json()


def test_super_admin_reads_price_and_subscription_of_a_company(db, client, super_admin, active_subscription):
  body = client.get(f'/subscription/company/{db.id}', headers=auth_header(super_admin)).get_json()

  assert body['price_cents'] == 4900
  assert body['subscription']['status'] == 'active'
  assert body['subscription']['active'] is True


def test_unknown_company_is_a_ko(db, client, super_admin):
  assert client.get('/subscription/company/999999', headers=auth_header(super_admin)).get_json()['status'] == 'ko'
  assert put_price(client, super_admin, 999999, price_cents=5000)['status'] == 'ko'


def test_only_the_super_admin_manages_the_price(db, client):
  admin = create_user(UserRole.ADMIN)

  assert client.get(f'/subscription/company/{db.id}', headers=auth_header(admin)).status_code == 403
  response = client.put(f'/subscription/company/{db.id}/price', json={'price_cents': 5000}, headers=auth_header(admin))
  assert response.status_code == 403


def test_new_price_moves_the_active_subscription_too(db, client, super_admin, active_subscription, stripe_updates):
  body = put_price(client, super_admin, db.id, price_cents=5900)

  assert body['price_cents'] == 5900
  assert stored_price(db) == 5900
  assert stripe_updates == [('sub_1', 5900)]


def test_without_an_active_subscription_nothing_is_sent_to_stripe(db, client, super_admin, stripe_updates):
  update(db, {'automatic_payment': True})

  body = put_price(client, super_admin, db.id, price_cents=5900)

  assert body['price_cents'] == 5900
  assert body['subscription']['status'] == 'none'
  assert stripe_updates == []


def test_a_canceled_subscription_is_not_updated(db, client, super_admin, active_subscription, stripe_updates):
  update(get_subscription(db.id), {'status': 'canceled'})

  put_price(client, super_admin, db.id, price_cents=5900)

  assert stripe_updates == []


def test_if_stripe_refuses_the_saved_price_does_not_change(db, client, super_admin, active_subscription, monkeypatch):
  def refuse(subscription_id, price_cents):
    raise stripe_client.stripe.StripeError('rifiutato', None)

  monkeypatch.setattr(stripe_client, 'update_subscription_price', refuse)

  body = put_price(client, super_admin, db.id, price_cents=5900)

  assert body['status'] == 'ko'
  assert body['message'].startswith('Errore Stripe')
  assert stored_price(db) == 4900


@pytest.mark.parametrize('payload', [{}, {'price_cents': 10}, {'price_cents': 'x'}, {'price_cents': True}])
def test_invalid_prices_are_refused(db, client, super_admin, payload):
  assert put_price(client, super_admin, db.id, **payload)['status'] == 'ko'


def test_stripe_client_swaps_the_price_of_the_item_without_prorations(monkeypatch):
  seen = {}
  item = {'id': 'si_1', 'price': {'product': 'prod_1'}}
  monkeypatch.setenv('STRIPE_SECRET_KEY', 'sk_test_x')
  monkeypatch.setattr(
    stripe_client.stripe.Subscription, 'retrieve', lambda subscription_id: {'items': {'data': [item]}}
  )
  monkeypatch.setattr(
    stripe_client.stripe.Subscription,
    'modify',
    lambda subscription_id, **kwargs: seen.update(kwargs) or SimpleNamespace(),
  )

  stripe_client.update_subscription_price('sub_1', 5900)

  assert seen['proration_behavior'] == 'none'
  assert seen['items'] == [
    {
      'id': 'si_1',
      'price_data': {'currency': 'eur', 'unit_amount': 5900, 'recurring': {'interval': 'month'}, 'product': 'prod_1'},
    }
  ]

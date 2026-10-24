"""Storico pagamenti di un'attività per il super admin, letto da Stripe (sostituito nei test)."""

from types import SimpleNamespace

import pytest

from database_api.operations import create

from src.database.schema import CompanySubscription
from src.end_points.subscription import stripe_client
from src.end_points.subscription.history import build_history, summarize

from tests.unit.factories import auth_header, create_super_admin, create_user
from src.database.enum import UserRole


JAN = 1767225600  # 2026-01-01
FEB = 1769904000  # 2026-02-01


def invoice(invoice_id, status='paid', created=JAN, amount=4900, attempts=1, **extra):
  return {
    'id': invoice_id,
    'number': f'N-{invoice_id}',
    'status': status,
    'created': created,
    'amount_paid': amount if status == 'paid' else 0,
    'amount_due': amount,
    'attempt_count': attempts,
    'hosted_invoice_url': f'https://stripe.test/{invoice_id}',
    'status_transitions': {'paid_at': created + 60 if status == 'paid' else None},
    **extra,
  }


def subscription_record(subscription_id='sub_1', status='active', **extra):
  return {
    'id': subscription_id,
    'status': status,
    'created': JAN,
    'items': {'data': [{'price': {'unit_amount': 4900}}]},
    **extra,
  }


@pytest.fixture
def super_admin(db):
  return create_super_admin()


@pytest.fixture
def customer(db):
  return create(CompanySubscription, {'company_id': db.id, 'stripe_customer_id': 'cus_1', 'status': 'active'})


def test_all_paid_on_first_attempt_is_regular():
  history = build_history([subscription_record()], [invoice('in_1'), invoice('in_2', created=FEB)])

  summary = history['summary']
  assert summary['regular'] is True
  assert (summary['paid_count'], summary['paid_total_cents']) == (2, 9800)
  assert (summary['unpaid_count'], summary['retried_count']) == (0, 0)
  assert summary['customer_since'].startswith('2026-01-01')


def test_an_unpaid_invoice_makes_the_history_irregular():
  summary = build_history([], [invoice('in_1'), invoice('in_2', status='open', created=FEB)])['summary']

  assert summary['regular'] is False
  assert summary['unpaid_count'] == 1


def test_a_payment_that_needed_a_retry_is_not_regular():
  summary = summarize(build_history([], [invoice('in_1', attempts=3)])['invoices'])

  assert summary['regular'] is False
  assert summary['retried_count'] == 1
  assert summary['paid_count'] == 1


def test_without_payments_there_is_nothing_regular_nor_a_start_date():
  summary = build_history([], [])['summary']

  assert summary['regular'] is False
  assert summary['customer_since'] is None


def test_drafts_are_left_out_and_unpaid_invoices_show_the_amount_due():
  history = build_history([], [invoice('in_1', status='draft'), invoice('in_2', status='uncollectible', amount=5900)])

  assert [item['id'] for item in history['invoices']] == ['in_2']
  assert history['invoices'][0]['amount_cents'] == 5900
  assert history['invoices'][0]['paid_at'] is None


def test_past_subscriptions_show_when_they_ended_and_at_what_price():
  history = build_history(
    [subscription_record('sub_old', status='canceled', canceled_at=FEB), subscription_record('sub_new')], []
  )

  old, new = history['subscriptions']
  assert (old['status'], old['price_cents']) == ('canceled', 4900)
  assert old['ended_at'].startswith('2026-02-01')
  assert new['ended_at'] is None


def test_super_admin_reads_the_history_of_a_company(db, client, super_admin, customer, monkeypatch):
  monkeypatch.setattr(stripe_client, 'list_subscriptions', lambda customer_id, limit=10: [subscription_record()])
  monkeypatch.setattr(stripe_client, 'list_invoices', lambda customer_id, limit=100: [invoice('in_1')])

  body = client.get(f'/subscription/company/{db.id}/history', headers=auth_header(super_admin)).get_json()

  assert body['status'] == 'ok'
  assert body['invoices'][0]['url'] == 'https://stripe.test/in_1'
  assert body['summary']['regular'] is True
  assert body['subscriptions'][0]['id'] == 'sub_1'


def test_a_company_that_never_subscribed_has_an_empty_history(db, client, super_admin):
  body = client.get(f'/subscription/company/{db.id}/history', headers=auth_header(super_admin)).get_json()

  assert body['status'] == 'ok'
  assert (body['invoices'], body['subscriptions']) == ([], [])


def test_stripe_failures_are_a_readable_ko(db, client, super_admin, customer, monkeypatch):
  def refuse(customer_id, limit=10):
    raise stripe_client.stripe.StripeError('rete', None)

  monkeypatch.setattr(stripe_client, 'list_subscriptions', refuse)

  body = client.get(f'/subscription/company/{db.id}/history', headers=auth_header(super_admin)).get_json()

  assert body['status'] == 'ko'


def test_only_the_super_admin_reads_the_history(db, client):
  admin = create_user(UserRole.ADMIN)

  assert client.get(f'/subscription/company/{db.id}/history', headers=auth_header(admin)).status_code == 403


def test_stripe_client_lists_invoices_and_subscriptions_of_a_customer(monkeypatch):
  seen = {}
  monkeypatch.setenv('STRIPE_SECRET_KEY', 'sk_test_x')
  monkeypatch.setattr(
    stripe_client.stripe.Invoice, 'list', lambda **kwargs: seen.update(invoices=kwargs) or SimpleNamespace(data=['i'])
  )
  monkeypatch.setattr(
    stripe_client.stripe.Subscription,
    'list',
    lambda **kwargs: seen.update(subscriptions=kwargs) or SimpleNamespace(data=['s']),
  )

  assert stripe_client.list_invoices('cus_1') == ['i']
  assert stripe_client.list_subscriptions('cus_1', limit=100) == ['s']
  assert seen['invoices'] == {'customer': 'cus_1', 'limit': 100}
  assert seen['subscriptions'] == {'customer': 'cus_1', 'status': 'all', 'limit': 100}

"""Pagamento automatico: flag e prezzo per attività (super admin), abbonamento Stripe (admin).

Stripe è sempre sostituito: nessuna rete, si verifica cosa il backend gli chiede
e cosa salva di ciò che risponde.
"""

import hashlib
import hmac
import json
import time
from datetime import datetime

import pytest

from database_api import Session
from database_api.operations import create, get_by_id, update

from src.database.enum import UserRole
from src.database.schema import Company, CompanySubscription
from src.database.queries import is_automatic_payment_enabled
from src.end_points.subscription import get_subscription, serialize_subscription, stripe_client

from tests.unit.factories import auth_header, create_company, create_super_admin, create_user


PAYMENT_OFF_MESSAGE = 'Pagamento automatico non attivo per questa attività'

LEGAL_PAYLOAD = {
  'legal_name': 'Attività SRL',
  'vat_number': '11122233344',
  'address': 'Via Test 1',
  'city': 'Bari (BA)',
}


@pytest.fixture
def payment_on(db):
  return update(db, {'automatic_payment': True, 'subscription_price_cents': 4900})


@pytest.fixture
def admin(db):
  return create_user(UserRole.ADMIN)


@pytest.fixture
def stripe_calls(monkeypatch):
  """Sostituisce il client Stripe e registra le chiamate."""
  calls = []
  monkeypatch.setattr(
    stripe_client, 'create_customer', lambda company_id, name: calls.append(('customer', name)) or 'cus_1'
  )
  monkeypatch.setattr(
    stripe_client,
    'create_checkout_url',
    lambda company_id, customer_id, price_cents: (
      calls.append(('checkout', customer_id, price_cents)) or 'https://stripe.test/checkout'
    ),
  )
  monkeypatch.setattr(
    stripe_client,
    'create_portal_url',
    lambda customer_id: calls.append(('portal', customer_id)) or 'https://stripe.test/portal',
  )
  return calls


def stripe_subscription(company_id, status='active', **extra):
  return {
    'id': 'sub_1',
    'status': status,
    'metadata': {'company_id': str(company_id)},
    'cancel_at_period_end': False,
    'current_period_end': 1893456000,
    **extra,
  }


def test_new_company_starts_without_automatic_payment(db):
  company = create_company()

  assert company.automatic_payment is False
  assert company.subscription_price_cents is None
  assert is_automatic_payment_enabled(db.id) is False
  assert is_automatic_payment_enabled(None) is False


def test_super_admin_sets_automatic_payment_and_price_on_a_company(db, client):
  super_admin = create_super_admin()

  created = client.post(
    '/company',
    json={
      'name': 'Con pagamento',
      'admin_nickname': 'admin-payment',
      'admin_password': 'pw',
      'automatic_payment': True,
      'subscription_price_cents': 4900,
      **LEGAL_PAYLOAD,
    },
    headers=auth_header(super_admin),
  ).get_json()
  assert created['company']['automatic_payment'] is True
  assert created['company']['subscription_price_cents'] == 4900

  company_id = created['company']['id']
  turned_off = client.put(
    f'/company/{company_id}',
    json={'name': 'Con pagamento', 'automatic_payment': False, 'subscription_price_cents': None},
    headers=auth_header(super_admin),
  ).get_json()
  assert turned_off['company']['automatic_payment'] is False
  assert turned_off['company'].get('subscription_price_cents') is None
  assert is_automatic_payment_enabled(company_id) is False


def test_automatic_payment_flag_must_be_boolean(db, client):
  response = client.put(
    f'/company/{db.id}',
    json={'name': db.name, 'automatic_payment': 'true'},
    headers=auth_header(create_super_admin()),
  ).get_json()

  assert response['status'] == 'ko'
  assert db.automatic_payment is False


@pytest.mark.parametrize('price', [10, 'cinquanta', 49.9, True])
def test_the_price_must_be_a_whole_amount_above_the_stripe_minimum(db, client, price):
  super_admin = create_super_admin()

  updated = client.put(
    f'/company/{db.id}', json={'name': db.name, 'subscription_price_cents': price}, headers=auth_header(super_admin)
  ).get_json()
  created = client.post(
    '/company',
    json={
      'name': 'Prezzo errato',
      'admin_nickname': 'admin-bad-price',
      'admin_password': 'pw',
      'subscription_price_cents': price,
      **LEGAL_PAYLOAD,
    },
    headers=auth_header(super_admin),
  ).get_json()

  assert updated['status'] == 'ko'
  assert created['status'] == 'ko'
  assert db.subscription_price_cents is None


@pytest.mark.parametrize(
  'method,path',
  [
    ('get', '/subscription'),
    ('post', '/subscription/checkout'),
    ('post', '/subscription/portal'),
    ('post', '/subscription/sync'),
  ],
)
def test_subscription_endpoints_are_closed_without_the_flag(db, client, admin, method, path):
  body = getattr(client, method)(path, json={}, headers=auth_header(admin)).get_json()

  assert body == {'status': 'ko', 'message': PAYMENT_OFF_MESSAGE}


def test_only_admins_manage_the_subscription(payment_on, client):
  operator = create_user(UserRole.OPERATOR)

  response = client.get('/subscription', headers=auth_header(operator))

  assert response.status_code == 403


def test_subscription_starts_empty_and_shows_the_company_price(payment_on, client, admin):
  body = client.get('/subscription', headers=auth_header(admin)).get_json()

  assert body['status'] == 'ok'
  assert (body['price_cents'], body['currency'], body['interval']) == (4900, 'eur', 'month')
  assert body['subscription']['status'] == 'none'
  assert body['subscription']['active'] is False


def test_checkout_creates_customer_once_and_charges_the_company_price(payment_on, client, admin, stripe_calls):
  first = client.post('/subscription/checkout', headers=auth_header(admin)).get_json()
  second = client.post('/subscription/checkout', headers=auth_header(admin)).get_json()

  assert first == {'status': 'ok', 'url': 'https://stripe.test/checkout'}
  assert second['status'] == 'ok'
  assert [call for call in stripe_calls if call[0] == 'customer'] == [('customer', payment_on.legal_name)]
  assert stripe_calls[1] == ('checkout', 'cus_1', 4900)
  assert get_subscription(payment_on.id).stripe_customer_id == 'cus_1'


def test_checkout_needs_a_price(payment_on, client, admin, stripe_calls):
  update(payment_on, {'subscription_price_cents': None})

  body = client.post('/subscription/checkout', headers=auth_header(admin)).get_json()

  assert body['status'] == 'ko'
  assert stripe_calls == []


def test_checkout_is_refused_while_a_subscription_is_active(payment_on, client, admin, stripe_calls):
  client.post('/subscription/checkout', headers=auth_header(admin))
  update(get_subscription(payment_on.id), {'status': 'active'})

  body = client.post('/subscription/checkout', headers=auth_header(admin)).get_json()

  assert body['status'] == 'ko'
  assert len([call for call in stripe_calls if call[0] == 'checkout']) == 1


def test_portal_needs_a_customer(payment_on, client, admin, stripe_calls):
  assert client.post('/subscription/portal', headers=auth_header(admin)).get_json()['status'] == 'ko'

  client.post('/subscription/checkout', headers=auth_header(admin))
  body = client.post('/subscription/portal', headers=auth_header(admin)).get_json()

  assert body == {'status': 'ok', 'url': 'https://stripe.test/portal'}


def test_sync_reads_the_latest_subscription_from_stripe(payment_on, client, admin, stripe_calls, monkeypatch):
  client.post('/subscription/checkout', headers=auth_header(admin))
  monkeypatch.setattr(stripe_client, 'list_subscriptions', lambda customer_id: [stripe_subscription(payment_on.id)])

  body = client.post('/subscription/sync', headers=auth_header(admin)).get_json()

  assert body['subscription']['active'] is True
  assert body['subscription']['current_period_end'].startswith('2030-')


def test_sync_without_a_customer_changes_nothing(payment_on, client, admin):
  body = client.post('/subscription/sync', headers=auth_header(admin)).get_json()

  assert body['subscription']['status'] == 'none'


def test_sync_keeps_the_state_when_stripe_has_no_subscription(payment_on, client, admin, stripe_calls, monkeypatch):
  client.post('/subscription/checkout', headers=auth_header(admin))
  monkeypatch.setattr(stripe_client, 'list_subscriptions', lambda customer_id: [])

  body = client.post('/subscription/sync', headers=auth_header(admin)).get_json()

  assert body['subscription']['status'] == 'none'


def test_webhook_rejects_a_bad_signature(db, client, monkeypatch):
  def refuse(payload, signature):
    raise ValueError('bad signature')

  monkeypatch.setattr(stripe_client, 'construct_event', refuse)

  response = client.post('/subscription/webhook', data=b'{}', headers={'Stripe-Signature': 'x'})

  assert response.status_code == 400


@pytest.mark.parametrize('event_type', ['customer.subscription.created', 'customer.subscription.updated'])
def test_webhook_stores_the_subscription(db, client, monkeypatch, event_type):
  event = {'type': event_type, 'data': {'object': stripe_subscription(db.id, cancel_at_period_end=True)}}
  monkeypatch.setattr(stripe_client, 'construct_event', lambda payload, signature: event)

  response = client.post('/subscription/webhook', data=b'{}', headers={'Stripe-Signature': 'x'})

  stored = get_subscription(db.id)
  assert response.get_json() == {'status': 'ok'}
  assert (stored.status, stored.stripe_subscription_id) == ('active', 'sub_1')
  assert stored.cancel_at_period_end is True


def test_webhook_marks_a_deleted_subscription_as_canceled(db, client, monkeypatch):
  events = iter(
    [
      {'type': 'customer.subscription.created', 'data': {'object': stripe_subscription(db.id)}},
      {'type': 'customer.subscription.deleted', 'data': {'object': stripe_subscription(db.id, status='canceled')}},
    ]
  )
  monkeypatch.setattr(stripe_client, 'construct_event', lambda payload, signature: next(events))

  client.post('/subscription/webhook', data=b'{}', headers={'Stripe-Signature': 'x'})
  client.post('/subscription/webhook', data=b'{}', headers={'Stripe-Signature': 'x'})

  assert get_subscription(db.id).status == 'canceled'
  assert serialize_subscription(get_subscription(db.id))['active'] is False


@pytest.mark.parametrize(
  'event',
  [
    {'type': 'invoice.paid', 'data': {'object': {}}},
    {'type': 'customer.subscription.updated', 'data': {'object': {'id': 'sub_x', 'status': 'active', 'metadata': {}}}},
  ],
)
def test_webhook_ignores_events_it_cannot_attribute(db, client, monkeypatch, event):
  monkeypatch.setattr(stripe_client, 'construct_event', lambda payload, signature: event)

  response = client.post('/subscription/webhook', data=b'{}', headers={'Stripe-Signature': 'x'})

  assert response.get_json() == {'status': 'ok'}
  assert get_subscription(db.id) is None


def test_subscription_fields_read_the_period_end_from_items_on_recent_api_versions():
  subscription = {
    'id': 'sub_2',
    'status': 'trialing',
    'metadata': {},
    'items': {'data': [{'current_period_end': 1893456000}]},
  }

  fields = stripe_client.subscription_fields(subscription)

  assert fields['current_period_end'].year == 2030
  assert fields['cancel_at_period_end'] is False


def test_subscription_fields_tolerate_a_missing_period_end():
  fields = stripe_client.subscription_fields({'id': 'sub_3', 'status': 'incomplete'})

  assert fields['current_period_end'] is None


def test_frontend_url_defaults_and_trims_the_trailing_slash(monkeypatch):
  monkeypatch.delenv('FRONTEND_URL', raising=False)
  assert stripe_client.frontend_url() == 'https://hubstra.it'

  monkeypatch.setenv('FRONTEND_URL', 'http://localhost:5173/')
  assert stripe_client.frontend_url() == 'http://localhost:5173'


def test_stripe_client_forwards_to_the_sdk(monkeypatch):
  """Le chiamate vere all'SDK, con l'SDK finto: parametri e chiave."""
  from types import SimpleNamespace

  seen = {}

  def record(name, result):
    def call(**kwargs):
      seen[name] = kwargs
      return result

    return call

  monkeypatch.setenv('STRIPE_SECRET_KEY', 'sk_test_x')
  monkeypatch.setenv('FRONTEND_URL', 'http://localhost:5173')
  monkeypatch.setattr(stripe_client.stripe.Customer, 'create', record('customer', SimpleNamespace(id='cus_9')))
  monkeypatch.setattr(stripe_client.stripe.Product, 'retrieve', lambda product_id: {'active': True})
  monkeypatch.setattr(stripe_client.stripe.checkout.Session, 'create', record('checkout', SimpleNamespace(url='u1')))
  monkeypatch.setattr(
    stripe_client.stripe.billing_portal.Session, 'create', record('portal', SimpleNamespace(url='u2'))
  )
  monkeypatch.setattr(stripe_client.stripe.Subscription, 'list', record('list', SimpleNamespace(data=['s'])))

  assert stripe_client.create_customer(7, 'Acme') == 'cus_9'
  assert stripe_client.create_checkout_url(7, 'cus_9', 4900) == 'u1'
  assert stripe_client.create_portal_url('cus_9') == 'u2'
  assert stripe_client.list_subscriptions('cus_9') == ['s']

  assert stripe_client.stripe.api_key == 'sk_test_x'
  assert seen['customer']['metadata'] == {'company_id': '7'}
  assert seen['checkout']['subscription_data']['metadata'] == {'company_id': '7'}
  assert seen['checkout']['line_items'][0]['price_data']['unit_amount'] == 4900
  assert seen['checkout']['line_items'][0]['price_data']['product'] == 'hubstra_subscription'
  assert seen['checkout']['success_url'] == 'http://localhost:5173/configuration?checkout=success'
  assert seen['portal']['return_url'] == 'http://localhost:5173/configuration'
  assert seen['list']['customer'] == 'cus_9'


def test_checkout_without_a_stripe_key_is_a_readable_ko(payment_on, client, admin, monkeypatch):
  monkeypatch.delenv('STRIPE_SECRET_KEY', raising=False)

  body = client.post('/subscription/checkout', headers=auth_header(admin)).get_json()

  assert body['status'] == 'ko'
  assert 'STRIPE_SECRET_KEY' in body['message']


def test_stripe_failures_are_a_readable_ko(payment_on, client, admin, stripe_calls, monkeypatch):
  def refuse(customer_id):
    raise stripe_client.stripe.StripeError('rete', None)

  client.post('/subscription/checkout', headers=auth_header(admin))
  monkeypatch.setattr(stripe_client, 'create_portal_url', refuse)

  body = client.post('/subscription/portal', headers=auth_header(admin)).get_json()

  assert body['status'] == 'ko'
  assert body['message'].startswith('Errore Stripe')


# --- Configurazione dell'attività da parte dell'admin ------------------------------


def test_admin_reads_his_own_company(db, client, admin):
  body = client.get('/company/me', headers=auth_header(admin)).get_json()

  assert body['status'] == 'ok'
  assert body['company']['id'] == db.id


def test_admin_updates_the_company_registry_but_not_modules_or_price(db, client, admin):
  body = client.put(
    '/company/me',
    json={
      'name': 'Nuovo nome',
      'city': 'Lecce (LE)',
      'rae': False,
      'automatic_planning': False,
      'automatic_payment': True,
      'subscription_price_cents': 100,
    },
    headers=auth_header(admin),
  ).get_json()

  assert body['status'] == 'ok'
  assert (body['company']['name'], body['company']['city']) == ('Nuovo nome', 'Lecce (LE)')
  assert body['company']['rae'] is True
  assert body['company']['automatic_planning'] is True
  assert body['company']['automatic_payment'] is False
  assert body['company'].get('subscription_price_cents') is None


def test_admin_cannot_blank_the_required_legal_fields(db, client, admin):
  body = client.put('/company/me', json={'name': db.name, 'vat_number': ''}, headers=auth_header(admin)).get_json()

  assert body['status'] == 'ko'
  assert 'Partita IVA' in body['message']


def test_only_admins_reach_the_company_configuration(db, client):
  operator = create_user(UserRole.OPERATOR)

  assert client.get('/company/me', headers=auth_header(operator)).status_code == 403
  assert client.put('/company/me', json={'name': 'x'}, headers=auth_header(operator)).status_code == 403


def test_super_admin_operating_on_a_company_edits_it_like_an_admin(db, client):
  super_admin = create_super_admin()

  body = client.put(
    '/company/me', json={'name': 'Da super admin'}, headers=auth_header(super_admin, company_id=db.id)
  ).get_json()

  assert body['company']['name'] == 'Da super admin'


def test_admin_serves_only_the_logo_of_his_company(db, client, admin):
  import os

  from api.storage import get_full_path

  from src import STATIC_FOLDER
  from src.end_points.company import LOGO_SUBFOLDER

  folder = get_full_path(STATIC_FOLDER, LOGO_SUBFOLDER)
  os.makedirs(folder, exist_ok=True)
  for name in (f'{db.id}.png', '999999.png'):
    with open(os.path.join(folder, name), 'wb') as logo_file:
      logo_file.write(b'png')

  own = client.get(f'/company/logo/{db.id}.png', headers=auth_header(admin))
  other = client.get('/company/logo/999999.png', headers=auth_header(admin))

  assert own.status_code == 200
  assert other.status_code == 403


def test_webhook_reads_events_made_of_non_dict_stripe_objects(db, client, monkeypatch):
  """L'SDK recente non restituisce dict: niente .get sull'abbonamento dell'evento."""

  class StripeLike:
    def __init__(self, data):
      self._data = data

    def __getitem__(self, key):
      value = self._data[key]
      return StripeLike(value) if isinstance(value, dict) else value

  event = StripeLike({'type': 'customer.subscription.updated', 'data': {'object': stripe_subscription(db.id)}})
  monkeypatch.setattr(stripe_client, 'construct_event', lambda payload, signature: event)

  response = client.post('/subscription/webhook', data=b'{}', headers={'Stripe-Signature': 'x'})

  assert response.get_json() == {'status': 'ok'}
  assert get_subscription(db.id).stripe_subscription_id == 'sub_1'


def test_the_subscription_product_is_created_once_with_a_fixed_id(monkeypatch):
  created = []
  monkeypatch.setenv('STRIPE_SECRET_KEY', 'sk_test_x')

  def missing(product_id):
    raise stripe_client.stripe.InvalidRequestError('assente', 'id', code='resource_missing')

  monkeypatch.setattr(stripe_client.stripe.Product, 'retrieve', missing)
  monkeypatch.setattr(stripe_client.stripe.Product, 'create', lambda **kwargs: created.append(kwargs))

  assert stripe_client.ensure_product() == 'hubstra_subscription'
  assert created == [{'id': 'hubstra_subscription', 'name': 'Abbonamento Hubstra'}]


def test_an_inactive_subscription_product_is_reactivated(monkeypatch):
  modified = []
  monkeypatch.setenv('STRIPE_SECRET_KEY', 'sk_test_x')
  monkeypatch.setattr(stripe_client.stripe.Product, 'retrieve', lambda product_id: {'active': False})
  monkeypatch.setattr(stripe_client.stripe.Product, 'modify', lambda product_id, **kwargs: modified.append(kwargs))

  stripe_client.ensure_product()

  assert modified == [{'active': True}]


def test_other_stripe_errors_on_the_product_are_not_swallowed(monkeypatch):
  monkeypatch.setenv('STRIPE_SECRET_KEY', 'sk_test_x')

  def broken(product_id):
    raise stripe_client.stripe.InvalidRequestError('altro', 'id', code='api_key_expired')

  monkeypatch.setattr(stripe_client.stripe.Product, 'retrieve', broken)

  with pytest.raises(stripe_client.stripe.InvalidRequestError):
    stripe_client.ensure_product()


def test_opening_the_page_realigns_the_state_to_stripe_without_a_webhook(
  payment_on, client, admin, stripe_calls, monkeypatch
):
  client.post('/subscription/checkout', headers=auth_header(admin))
  monkeypatch.setattr(stripe_client, 'list_subscriptions', lambda customer_id: [stripe_subscription(payment_on.id)])

  body = client.get('/subscription', headers=auth_header(admin)).get_json()

  assert body['subscription']['active'] is True
  assert get_subscription(payment_on.id).stripe_subscription_id == 'sub_1'


def test_opening_the_page_shows_the_last_known_state_if_stripe_is_down(
  payment_on, client, admin, stripe_calls, monkeypatch
):
  client.post('/subscription/checkout', headers=auth_header(admin))

  def down(customer_id):
    raise stripe_client.stripe.StripeError('rete', None)

  monkeypatch.setattr(stripe_client, 'list_subscriptions', down)

  body = client.get('/subscription', headers=auth_header(admin)).get_json()

  assert body['status'] == 'ok'
  assert body['subscription']['status'] == 'none'


def test_opening_the_page_without_a_stripe_key_still_works(payment_on, client, admin, stripe_calls, monkeypatch):
  client.post('/subscription/checkout', headers=auth_header(admin))
  monkeypatch.delenv('STRIPE_SECRET_KEY', raising=False)

  assert client.get('/subscription', headers=auth_header(admin)).get_json()['status'] == 'ok'


# --- webhook: firma, segreto, idempotenza, ordine degli eventi ---


WEBHOOK_SECRET = 'whsec_test'


def signed_headers(payload: bytes, secret: str):
  """Firma Stripe vera (v1 = HMAC-SHA256 di "<t>.<body>"), costruita con la chiave data."""
  timestamp = int(time.time())
  digest = hmac.new(secret.encode(), f'{timestamp}.'.encode() + payload, hashlib.sha256).hexdigest()
  return {'Stripe-Signature': f't={timestamp},v1={digest}', 'Content-Type': 'application/json'}


def event_payload(company_id, event_id='evt_1', created=1893000000, event_type='customer.subscription.updated', **sub):
  return json.dumps(
    {
      'id': event_id,
      'object': 'event',
      'type': event_type,
      'created': created,
      'data': {'object': stripe_subscription(company_id, **sub)},
    }
  ).encode()


def post_signed(client, payload, secret=WEBHOOK_SECRET):
  return client.post('/subscription/webhook', data=payload, headers=signed_headers(payload, secret))


def test_webhook_applies_an_event_with_a_valid_signature(db, client, monkeypatch):
  monkeypatch.setenv('STRIPE_WEBHOOK_SECRET', WEBHOOK_SECRET)

  response = post_signed(client, event_payload(db.id))

  assert response.get_json() == {'status': 'ok'}
  assert get_subscription(db.id).status == 'active'


def test_webhook_rejects_a_signature_made_with_another_key(db, client, monkeypatch):
  monkeypatch.setenv('STRIPE_WEBHOOK_SECRET', WEBHOOK_SECRET)

  response = post_signed(client, event_payload(db.id), secret='whsec_altro')

  assert response.status_code == 400
  assert get_subscription(db.id) is None


@pytest.mark.parametrize('secret_value', [None, ''])
def test_webhook_without_a_secret_accepts_nothing_even_if_signed_with_an_empty_key(
  db, client, monkeypatch, secret_value
):
  if secret_value is None:
    monkeypatch.delenv('STRIPE_WEBHOOK_SECRET', raising=False)
  else:
    monkeypatch.setenv('STRIPE_WEBHOOK_SECRET', secret_value)

  response = post_signed(client, event_payload(db.id), secret='')

  assert response.status_code == 503
  assert get_subscription(db.id) is None


def test_webhook_for_a_missing_company_is_confirmed_not_a_500(db, client, monkeypatch):
  monkeypatch.setenv('STRIPE_WEBHOOK_SECRET', WEBHOOK_SECRET)

  response = post_signed(client, event_payload(999999))

  assert response.status_code == 200
  assert get_subscription(999999) is None


def test_webhook_with_a_malformed_company_id_is_confirmed(db, client, monkeypatch):
  monkeypatch.setenv('STRIPE_WEBHOOK_SECRET', WEBHOOK_SECRET)

  assert post_signed(client, event_payload('abc')).status_code == 200


def test_webhook_applies_the_same_event_only_once(db, client, monkeypatch):
  monkeypatch.setenv('STRIPE_WEBHOOK_SECRET', WEBHOOK_SECRET)
  post_signed(client, event_payload(db.id, event_id='evt_dup', status='active'))
  update(get_subscription(db.id), {'status': 'past_due'})

  # Stessa consegna ripetuta da Stripe: non deve sovrascrivere ciò che è successo dopo.
  post_signed(client, event_payload(db.id, event_id='evt_dup', status='active'))

  assert get_subscription(db.id).status == 'past_due'


def test_webhook_ignores_an_event_older_than_the_applied_state(db, client, monkeypatch):
  monkeypatch.setenv('STRIPE_WEBHOOK_SECRET', WEBHOOK_SECRET)
  post_signed(client, event_payload(db.id, 'evt_del', 1893000100, 'customer.subscription.deleted', status='canceled'))

  # Un `updated` nato prima della cancellazione, consegnato dopo: non riapre l'abbonamento.
  post_signed(client, event_payload(db.id, 'evt_upd', 1893000000, status='active'))

  assert get_subscription(db.id).status == 'canceled'


def test_get_or_create_subscription_keeps_a_single_row(db):
  from src.end_points.subscription import _get_or_create_subscription

  first = _get_or_create_subscription(db.id)
  second = _get_or_create_subscription(db.id)

  assert first.id == second.id
  with Session() as session:
    assert session.query(CompanySubscription).filter_by(company_id=db.id).count() == 1


# --- flag e prezzo contro Stripe ---


@pytest.fixture
def live_subscription(payment_on):
  return create(
    CompanySubscription,
    {'company_id': payment_on.id, 'stripe_customer_id': 'cus_1', 'stripe_subscription_id': 'sub_1', 'status': 'active'},
  )


@pytest.fixture
def stripe_price_updates(monkeypatch):
  calls = []
  monkeypatch.setattr(stripe_client, 'update_subscription_price', lambda *args: calls.append(args))
  return calls


def put_company(client, company, **changes):
  return client.put(
    f'/company/{company.id}', json={'name': company.name, **changes}, headers=auth_header(create_super_admin())
  ).get_json()


def test_flag_cannot_be_turned_off_while_stripe_is_charging(payment_on, live_subscription, client):
  body = put_company(client, payment_on, automatic_payment=False)

  assert body['status'] == 'ko'
  assert is_automatic_payment_enabled(payment_on.id) is True


def test_flag_can_be_turned_off_once_the_subscription_ends_at_period_end(payment_on, live_subscription, client):
  update(live_subscription, {'cancel_at_period_end': True})

  assert put_company(client, payment_on, automatic_payment=False)['status'] == 'ok'
  assert is_automatic_payment_enabled(payment_on.id) is False


def test_flag_can_be_turned_off_when_the_subscription_is_canceled(payment_on, live_subscription, client):
  update(live_subscription, {'status': 'canceled'})

  assert put_company(client, payment_on, automatic_payment=False)['status'] == 'ok'


def test_price_changed_from_the_company_form_goes_through_stripe(
  payment_on, live_subscription, client, stripe_price_updates
):
  body = put_company(client, payment_on, subscription_price_cents=5900)

  assert body['company']['subscription_price_cents'] == 5900
  assert stripe_price_updates == [('sub_1', 5900)]


def test_price_changed_from_the_company_form_is_not_saved_if_stripe_refuses(
  payment_on, live_subscription, client, monkeypatch
):
  def refuse(subscription_id, price_cents):
    raise stripe_client.stripe.StripeError('rifiutato', None)

  monkeypatch.setattr(stripe_client, 'update_subscription_price', refuse)

  body = put_company(client, payment_on, subscription_price_cents=5900)

  assert body['status'] == 'ko'
  assert get_by_id(Company, payment_on.id).subscription_price_cents == 4900


def test_the_price_cannot_be_removed_while_stripe_is_charging(payment_on, live_subscription, client):
  assert put_company(client, payment_on, subscription_price_cents=None)['status'] == 'ko'


def test_unchanged_price_does_not_call_stripe(payment_on, live_subscription, client, stripe_price_updates):
  put_company(client, payment_on, subscription_price_cents=4900)

  assert stripe_price_updates == []


def test_a_past_due_subscription_also_gets_the_new_price_on_stripe(
  payment_on, live_subscription, client, stripe_price_updates
):
  update(live_subscription, {'status': 'past_due'})

  body = client.put(
    f'/subscription/company/{payment_on.id}/price',
    json={'price_cents': 5900},
    headers=auth_header(create_super_admin()),
  ).get_json()

  assert body['price_cents'] == 5900
  assert stripe_price_updates == [('sub_1', 5900)]


# --- chiamate a Stripe: timeout e frequenza ---


def test_stripe_calls_have_a_timeout_and_network_retries(monkeypatch):
  monkeypatch.setenv('STRIPE_SECRET_KEY', 'sk_test_x')

  stripe_client._configure()

  assert stripe_client.stripe.max_network_retries == stripe_client.MAX_NETWORK_RETRIES
  assert stripe_client.stripe.default_http_client._timeout == stripe_client.API_TIMEOUT_SECONDS


@pytest.fixture
def stripe_reads(payment_on, client, admin, stripe_calls, monkeypatch):
  client.post('/subscription/checkout', headers=auth_header(admin))
  reads = []
  monkeypatch.setattr(
    stripe_client,
    'list_subscriptions',
    lambda customer_id: reads.append(customer_id) or [stripe_subscription(payment_on.id)],
  )
  return reads


def test_opening_the_page_does_not_call_stripe_while_the_state_is_fresh(payment_on, client, admin, stripe_reads):
  for _ in range(3):
    client.get('/subscription', headers=auth_header(admin))

  assert len(stripe_reads) == 1


def test_opening_the_page_rereads_a_stale_state(payment_on, client, admin, stripe_reads):
  client.get('/subscription', headers=auth_header(admin))
  update(get_subscription(payment_on.id), {'synced_at': datetime(2000, 1, 1)})

  client.get('/subscription', headers=auth_header(admin))

  assert len(stripe_reads) == 2


def test_explicit_sync_always_reads_stripe(payment_on, client, admin, stripe_reads):
  client.post('/subscription/sync', headers=auth_header(admin))
  client.post('/subscription/sync', headers=auth_header(admin))

  assert len(stripe_reads) == 2

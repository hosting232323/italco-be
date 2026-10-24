import os
from datetime import datetime, timezone

import stripe

from .plans import CURRENCY, INTERVAL


class StripeNotConfigured(Exception):
  pass


# Unico punto che parla con Stripe: i test lo sostituiscono, nessuna rete.
def _configure() -> None:
  api_key = os.environ.get('STRIPE_SECRET_KEY')
  if not api_key:
    raise StripeNotConfigured()
  stripe.api_key = api_key


def frontend_url() -> str:
  return os.environ.get('FRONTEND_URL', 'https://hubstra.it').rstrip('/')


def create_customer(company_id: int, name: str) -> str:
  _configure()
  return stripe.Customer.create(name=name, metadata={'company_id': str(company_id)}).id


def create_checkout_url(company_id: int, customer_id: str, price_cents: int) -> str:
  _configure()
  base = frontend_url()
  session = stripe.checkout.Session.create(
    mode='subscription',
    customer=customer_id,
    line_items=[
      {
        'quantity': 1,
        'price_data': {
          'currency': CURRENCY,
          'unit_amount': price_cents,
          'recurring': {'interval': INTERVAL},
          'product_data': {'name': 'Abbonamento Hubstra'},
        },
      }
    ],
    # I metadata sull'abbonamento permettono al webhook di risalire alla company
    # senza altre letture.
    subscription_data={'metadata': {'company_id': str(company_id)}},
    success_url=f'{base}/configuration?checkout=success',
    cancel_url=f'{base}/configuration?checkout=cancel',
  )
  return session.url


def create_portal_url(customer_id: str) -> str:
  _configure()
  return stripe.billing_portal.Session.create(customer=customer_id, return_url=f'{frontend_url()}/configuration').url


def list_subscriptions(customer_id: str) -> list:
  _configure()
  return list(stripe.Subscription.list(customer=customer_id, status='all', limit=10).data)


def update_subscription_price(subscription_id: str, price_cents: int) -> None:
  """Cambia il prezzo di un abbonamento già attivo, senza disdirlo.

  Stripe non modifica un prezzo esistente: si sostituisce quello dell'item con
  uno nuovo sullo stesso prodotto. proration_behavior='none' fa partire il nuovo
  importo dal prossimo rinnovo, senza addebiti né crediti immediati: il cliente
  non vede interruzioni e non deve riabbonarsi.
  """
  _configure()
  item = stripe.Subscription.retrieve(subscription_id)['items']['data'][0]
  stripe.Subscription.modify(
    subscription_id,
    items=[
      {
        'id': item['id'],
        'price_data': {
          'currency': CURRENCY,
          'unit_amount': price_cents,
          'recurring': {'interval': INTERVAL},
          'product': item['price']['product'],
        },
      }
    ],
    proration_behavior='none',
  )


def construct_event(payload: bytes, signature: str):
  return stripe.Webhook.construct_event(payload, signature, os.environ.get('STRIPE_WEBHOOK_SECRET', ''))


def _get(obj, key, default=None):
  try:
    value = obj[key]
  except (KeyError, TypeError):
    return default
  return default if value is None else value


def subscription_fields(subscription) -> dict:
  """Campi che interessano di un abbonamento Stripe, già nel formato del DB.

  current_period_end sta sull'abbonamento nelle API vecchie e sugli item in
  quelle recenti: si legge dove c'è.
  """
  period_end = _get(subscription, 'current_period_end')
  if period_end is None:
    items = _get(_get(subscription, 'items', {}), 'data', [])
    period_end = _get(items[0], 'current_period_end') if items else None

  return {
    'stripe_subscription_id': subscription['id'],
    'status': subscription['status'],
    'cancel_at_period_end': bool(_get(subscription, 'cancel_at_period_end', False)),
    'current_period_end': (
      datetime.fromtimestamp(period_end, tz=timezone.utc).replace(tzinfo=None) if period_end else None
    ),
  }

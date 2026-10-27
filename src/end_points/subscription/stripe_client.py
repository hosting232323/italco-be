import os
from datetime import datetime, timezone

import stripe

from .plans import CURRENCY, INTERVAL


class StripeNotConfigured(Exception):
  pass


# Senza timeout l'SDK aspetta 80 secondi: una Stripe lenta bloccherebbe un worker
# per richiesta. Pochi secondi e un paio di tentativi sui soli errori di rete.
API_TIMEOUT_SECONDS = 10
MAX_NETWORK_RETRIES = 2


# Unico punto che parla con Stripe: i test lo sostituiscono, nessuna rete.
def _configure() -> None:
  api_key = os.environ.get('STRIPE_SECRET_KEY')
  if not api_key:
    raise StripeNotConfigured()
  stripe.api_key = api_key
  stripe.max_network_retries = MAX_NETWORK_RETRIES
  stripe.default_http_client = stripe.http_client.RequestsClient(timeout=API_TIMEOUT_SECONDS)


# Prodotto unico dell'abbonamento, con ID fisso così si ritrova senza salvarlo nel DB.
# Serve un prodotto vero: quelli creati al volo da price_data/product_data risultano
# inattivi, e Stripe rifiuta nuovi abbonamenti (o lo spostamento di uno esistente)
# su un prodotto inattivo.
PRODUCT_ID = 'hubstra_subscription'
PRODUCT_NAME = 'Abbonamento Hubstra'


def ensure_product() -> str:
  _configure()
  try:
    if not stripe.Product.retrieve(PRODUCT_ID)['active']:
      stripe.Product.modify(PRODUCT_ID, active=True)
  except stripe.InvalidRequestError as error:
    if error.code != 'resource_missing':
      raise
    stripe.Product.create(id=PRODUCT_ID, name=PRODUCT_NAME)
  return PRODUCT_ID


def frontend_url() -> str:
  # Vuota (variabile CI non definita) vale come assente.
  return (os.environ.get('FRONTEND_URL') or 'https://hubstra.it').rstrip('/')


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
          'product': ensure_product(),
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


def list_subscriptions(customer_id: str, limit: int = 10) -> list:
  _configure()
  return list(stripe.Subscription.list(customer=customer_id, status='all', limit=limit).data)


def list_invoices(customer_id: str, limit: int = 100) -> list:
  _configure()
  return list(stripe.Invoice.list(customer=customer_id, limit=limit).data)


def update_subscription_price(subscription_id: str, price_cents: int) -> None:
  """Cambia il prezzo di un abbonamento già attivo, senza disdirlo.

  Stripe non modifica un prezzo esistente: si sostituisce quello dell'item con
  uno nuovo, sul prodotto attivo (gli abbonamenti nati con prodotti al volo, poi
  inattivi, vengono così spostati su quello vero). proration_behavior='none' fa partire il nuovo
  importo dal prossimo rinnovo, senza addebiti né crediti immediati: il cliente
  non vede interruzioni e non deve riabbonarsi.
  """
  _configure()
  item = stripe.Subscription.retrieve(subscription_id)['items']['data'][0]
  product = ensure_product()
  stripe.Subscription.modify(
    subscription_id,
    items=[
      {
        'id': item['id'],
        'price_data': {
          'currency': CURRENCY,
          'unit_amount': price_cents,
          'recurring': {'interval': INTERVAL},
          'product': product,
        },
      }
    ],
    proration_behavior='none',
  )


def construct_event(payload: bytes, signature: str):
  # Senza segreto la firma si calcolerebbe con una chiave vuota, che chiunque
  # conosce: il webhook non accetta nulla finché non è configurato.
  secret = os.environ.get('STRIPE_WEBHOOK_SECRET')
  if not secret:
    raise StripeNotConfigured()
  return stripe.Webhook.construct_event(payload, signature, secret)


def get_field(obj, key, default=None):
  # Gli oggetti dell'SDK recente non sono dict (niente .get): si legge per chiave.
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
  period_end = get_field(subscription, 'current_period_end')
  if period_end is None:
    items = get_field(get_field(subscription, 'items', {}), 'data', [])
    period_end = get_field(items[0], 'current_period_end') if items else None

  return {
    'stripe_subscription_id': subscription['id'],
    'status': subscription['status'],
    'cancel_at_period_end': bool(get_field(subscription, 'cancel_at_period_end', False)),
    'current_period_end': (
      datetime.fromtimestamp(period_end, tz=timezone.utc).replace(tzinfo=None) if period_end else None
    ),
  }

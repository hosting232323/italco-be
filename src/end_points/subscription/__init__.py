import logging
from datetime import datetime, timedelta, timezone
from functools import wraps

import stripe
from flask import Blueprint, request
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from database_api import Session, current_scope
from database_api.operations import create, update

from .. import flask_session_authentication
from ...database.enum import UserRole
from ...database.schema import Company, CompanySubscription, StripeEvent
from . import stripe_client
from .history import build_history
from .plans import CURRENCY, INTERVAL, MIN_PRICE_CENTS, is_valid_price


logger = logging.getLogger(__name__)

subscription_bp = Blueprint('subscription_bp', __name__)

# Stati Stripe in cui l'attività sta pagando (o è in prova): gli altri
# (past_due, canceled, incomplete...) non contano come abbonamento attivo.
ACTIVE_STATUSES = ('active', 'trialing')

# Stati in cui Stripe può ancora addebitare: finché uno di questi è in corso
# (e non è già disdetto a fine periodo) il pagamento automatico non si spegne.
BILLING_STATUSES = ('active', 'trialing', 'past_due', 'unpaid', 'paused')

# Oltre questo tempo dall'ultimo stato certo, aprire la pagina rilegge Stripe.
# Col webhook configurato lo stato è sempre fresco e Stripe non viene chiamato.
SYNC_MAX_AGE = timedelta(minutes=5)

WEBHOOK_SUBSCRIPTION_EVENTS = (
  'customer.subscription.created',
  'customer.subscription.updated',
  'customer.subscription.deleted',
)


def stripe_errors(func):
  """Un problema lato Stripe (chiave mancante, rete, richiesta rifiutata) è un
  ko leggibile per l'admin, non un 500 che il frontend mostra come errore generico."""

  @wraps(func)
  def wrapper(*args, **kwargs):
    try:
      return func(*args, **kwargs)
    except stripe_client.StripeNotConfigured:
      return {'status': 'ko', 'message': 'Stripe non configurato: manca STRIPE_SECRET_KEY sul server'}
    except stripe.StripeError as error:
      return {'status': 'ko', 'message': f'Errore Stripe: {error.user_message or error}'}

  return wrapper


def get_price_cents(company_id: int) -> int | None:
  with Session() as session:
    return session.get(Company, company_id).subscription_price_cents


def get_subscription(company_id: int) -> CompanySubscription | None:
  with Session() as session:
    return session.query(CompanySubscription).filter_by(company_id=company_id).first()


def serialize_subscription(subscription: CompanySubscription | None) -> dict:
  if not subscription:
    return {'status': 'none', 'active': False, 'current_period_end': None, 'cancel_at_period_end': False}

  return {
    'status': subscription.status,
    'active': subscription.status in ACTIVE_STATUSES,
    'current_period_end': subscription.current_period_end.isoformat() if subscription.current_period_end else None,
    'cancel_at_period_end': subscription.cancel_at_period_end,
  }


def has_billing_subscription(company_id: int) -> bool:
  """Stripe sta (o può ancora) addebitando questa attività: abbonamento in
  corso e non già disdetto a fine periodo."""
  subscription = get_subscription(company_id)
  return bool(subscription and subscription.status in BILLING_STATUSES and not subscription.cancel_at_period_end)


def _utcnow() -> datetime:
  return datetime.now(timezone.utc).replace(tzinfo=None)


def _get_or_create_subscription(company_id: int) -> CompanySubscription:
  # Due richieste insieme (doppio click su "Abbonati") non devono creare due righe:
  # l'insert ignora il conflitto sull'unico company_id e si rilegge la riga vincente.
  existing = get_subscription(company_id)
  if existing:
    return existing

  with Session() as session:
    session.execute(insert(CompanySubscription).values(company_id=company_id).on_conflict_do_nothing())
    session.commit()
  return get_subscription(company_id)


def _get_or_create_customer(company_id: int) -> str:
  subscription = _get_or_create_subscription(company_id)
  if subscription.stripe_customer_id:
    return subscription.stripe_customer_id

  with Session() as session:
    company: Company = session.get(Company, company_id)
    name = company.legal_name or company.name
  customer_id = stripe_client.create_customer(company_id, name)
  update(subscription, {'stripe_customer_id': customer_id})
  return customer_id


def refresh_from_stripe(company_id: int, force: bool = True) -> None:
  """Riallinea lo stato locale a quello di Stripe (se l'attività ha un cliente).

  Il webhook fa lo stesso, ma non sempre arriva: in locale non è configurato, e
  chi paga può non tornare sulla pagina di conferma. Con force=False Stripe si
  chiama solo se lo stato locale è più vecchio di SYNC_MAX_AGE."""
  subscription = get_subscription(company_id)
  if not subscription or not subscription.stripe_customer_id:
    return
  if not force and subscription.synced_at and _utcnow() - subscription.synced_at < SYNC_MAX_AGE:
    return

  # L'istante è preso prima della lettura: un evento nato mentre Stripe risponde
  # non deve risultare più vecchio dello stato appena scritto.
  read_at = _utcnow()
  stripe_subscriptions = stripe_client.list_subscriptions(subscription.stripe_customer_id)
  if stripe_subscriptions:
    # Stripe le elenca dalla più recente: conta quella, anche dopo una
    # disdetta seguita da una nuova sottoscrizione.
    _apply_subscription(company_id, stripe_subscriptions[0], read_at)
  else:
    update(subscription, {'synced_at': read_at})


def _apply_subscription(company_id: int, stripe_subscription, state_at: datetime) -> bool:
  """Scrive lo stato Stripe, a meno che il DB non ne abbia già uno più recente
  (un `updated` in ritardo non deve riaprire un abbonamento già cancellato)."""
  subscription = _get_or_create_subscription(company_id)
  if subscription.synced_at and state_at < subscription.synced_at:
    return False
  update(subscription, {**stripe_client.subscription_fields(stripe_subscription), 'synced_at': state_at})
  return True


@subscription_bp.route('', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN], automatic_payment_required=True)
def get_company_subscription(_):
  company_id = current_scope()['company_id']
  # Se Stripe non risponde si mostra l'ultimo stato noto: leggere la pagina non
  # deve fallire per un problema di rete. Stripe si richiama solo a stato scaduto.
  try:
    refresh_from_stripe(company_id, force=False)
  except (stripe_client.StripeNotConfigured, stripe.StripeError):
    pass
  return {
    'status': 'ok',
    'price_cents': get_price_cents(company_id),
    'currency': CURRENCY,
    'interval': INTERVAL,
    'subscription': serialize_subscription(get_subscription(company_id)),
  }


@subscription_bp.route('checkout', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN], automatic_payment_required=True)
@stripe_errors
def checkout(_):
  company_id = current_scope()['company_id']
  price_cents = get_price_cents(company_id)
  if not price_cents:
    return {'status': 'ko', 'message': "Il prezzo dell'abbonamento non è ancora stato definito"}
  if serialize_subscription(get_subscription(company_id))['active']:
    return {'status': 'ko', 'message': 'Abbonamento già attivo: usa la gestione abbonamento per modificarlo'}

  customer_id = _get_or_create_customer(company_id)
  return {'status': 'ok', 'url': stripe_client.create_checkout_url(company_id, customer_id, price_cents)}


@subscription_bp.route('portal', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN], automatic_payment_required=True)
@stripe_errors
def portal(_):
  subscription = get_subscription(current_scope()['company_id'])
  if not subscription or not subscription.stripe_customer_id:
    return {'status': 'ko', 'message': 'Nessun abbonamento da gestire'}
  return {'status': 'ok', 'url': stripe_client.create_portal_url(subscription.stripe_customer_id)}


@subscription_bp.route('sync', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN], automatic_payment_required=True)
@stripe_errors
def sync(_):
  """Rilegge lo stato da Stripe. Al ritorno da Checkout il webhook può non
  essere ancora arrivato (o, in locale, non essere configurato): la pagina
  chiama questo per mostrare subito lo stato reale."""
  company_id = current_scope()['company_id']
  refresh_from_stripe(company_id)
  return {'status': 'ok', 'subscription': serialize_subscription(get_subscription(company_id))}


def _company_subscription_info(company_id: int) -> dict:
  return {
    'status': 'ok',
    'price_cents': get_price_cents(company_id),
    'subscription': serialize_subscription(get_subscription(company_id)),
  }


# Gestione del prezzo da parte del super admin: non ha una company attiva (si sceglie
# l'attività dalla tabella), quindi niente scope e niente flag richiesto.
@subscription_bp.route('company/<company_id>', methods=['GET'])
@flask_session_authentication([UserRole.SUPER_ADMIN], tenant_required=False)
def get_company_subscription_info(_, company_id):
  with Session() as session:
    if not session.get(Company, int(company_id)):
      return {'status': 'ko', 'message': 'Company non trovata'}
  return _company_subscription_info(int(company_id))


@subscription_bp.route('company/<company_id>/history', methods=['GET'])
@flask_session_authentication([UserRole.SUPER_ADMIN], tenant_required=False)
@stripe_errors
def get_company_payment_history(_, company_id):
  """Abbonamenti e fatture dell'attività, letti da Stripe: da quando paga e se ha
  sempre saldato. Senza un cliente Stripe (mai abbonata) lo storico è vuoto."""
  subscription = get_subscription(int(company_id))
  customer_id = subscription.stripe_customer_id if subscription else None
  subscriptions = stripe_client.list_subscriptions(customer_id, limit=100) if customer_id else []
  invoices = stripe_client.list_invoices(customer_id) if customer_id else []
  return {'status': 'ok', **build_history(subscriptions, invoices)}


def push_price_to_stripe(company_id: int, price_cents: int) -> None:
  """Porta su Stripe il nuovo prezzo di un abbonamento ancora vivo (anche past_due:
  il prossimo tentativo userebbe il vecchio importo). Da chiamare PRIMA di salvare
  il prezzo: se Stripe rifiuta, resta quello di prima e nessun lato è a metà."""
  subscription = get_subscription(company_id)
  if subscription and subscription.stripe_subscription_id and subscription.status in BILLING_STATUSES:
    stripe_client.update_subscription_price(subscription.stripe_subscription_id, price_cents)


def set_company_price(company: Company, price_cents: int) -> None:
  push_price_to_stripe(company.id, price_cents)
  update(company, {'subscription_price_cents': price_cents})


@subscription_bp.route('company/<company_id>/price', methods=['PUT'])
@flask_session_authentication([UserRole.SUPER_ADMIN], tenant_required=False)
@stripe_errors
def update_company_price(_, company_id):
  """Fissa il prezzo mensile di un'attività.

  Vale per i nuovi abbonamenti e anche per quello già attivo, che passa al nuovo
  importo dal prossimo rinnovo (vedi update_subscription_price).
  """
  company_id = int(company_id)
  payload = request.get_json(silent=True) or {}
  price_cents = payload.get('price_cents')
  if not is_valid_price(price_cents):
    return {'status': 'ko', 'message': f"Il prezzo dell'abbonamento deve essere di almeno {MIN_PRICE_CENTS} centesimi"}

  with Session() as session:
    company = session.get(Company, company_id)
  if not company:
    return {'status': 'ko', 'message': 'Company non trovata'}

  set_company_price(company, price_cents)
  return _company_subscription_info(company_id)


def _event_seen(event_id: str) -> bool:
  with Session() as session:
    return session.query(StripeEvent).filter_by(event_id=event_id).first() is not None


def _mark_event_seen(event_id: str) -> None:
  try:
    create(StripeEvent, {'event_id': event_id})
  except IntegrityError:
    # Lo stesso evento consegnato due volte in parallelo: l'altra richiesta l'ha già registrato.
    pass


def _handle_subscription_event(event) -> None:
  event_id = stripe_client.get_field(event, 'id')
  if event_id and _event_seen(event_id):
    return

  stripe_subscription = event['data']['object']
  company_id = stripe_client.get_field(stripe_client.get_field(stripe_subscription, 'metadata', {}), 'company_id')
  if not company_id:
    return

  # Un evento che non si può applicare (company cancellata, metadata sporchi) va
  # loggato e confermato: un 500 farebbe ritentare Stripe per giorni, inutilmente.
  try:
    company_id = int(company_id)
  except (TypeError, ValueError):
    logger.warning('Webhook Stripe %s: company_id non valido %r', event_id, company_id)
    return
  with Session() as session:
    if not session.get(Company, company_id):
      logger.warning('Webhook Stripe %s: company %s inesistente', event_id, company_id)
      return

  created = stripe_client.get_field(event, 'created')
  state_at = datetime.fromtimestamp(created, tz=timezone.utc).replace(tzinfo=None) if created else _utcnow()
  if not _apply_subscription(company_id, stripe_subscription, state_at):
    logger.info('Webhook Stripe %s: più vecchio dello stato salvato, ignorato', event_id)
  if event_id:
    _mark_event_seen(event_id)


# Endpoint pubblico: l'unica autenticazione è la firma Stripe sul body grezzo.
@subscription_bp.route('webhook', methods=['POST'])
def webhook():
  try:
    event = stripe_client.construct_event(request.get_data(), request.headers.get('Stripe-Signature', ''))
  except stripe_client.StripeNotConfigured:
    logger.error('Webhook Stripe rifiutato: STRIPE_WEBHOOK_SECRET non configurato')
    return {'status': 'ko', 'message': 'Webhook non configurato'}, 503
  except Exception:
    return {'status': 'ko', 'message': 'Firma non valida'}, 400

  if event['type'] in WEBHOOK_SUBSCRIPTION_EVENTS:
    _handle_subscription_event(event)

  return {'status': 'ok'}

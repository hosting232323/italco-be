from flask import Blueprint, request

from database_api import Session, current_scope
from database_api.operations import create, update

from .. import flask_session_authentication
from ...database.enum import UserRole
from ...database.schema import Company, CompanySubscription
from . import stripe_client
from .plans import PLANS, public_plans


subscription_bp = Blueprint('subscription_bp', __name__)

# Stati Stripe in cui l'attività sta pagando (o è in prova): gli altri
# (past_due, canceled, incomplete...) non contano come abbonamento attivo.
ACTIVE_STATUSES = ('active', 'trialing')

WEBHOOK_SUBSCRIPTION_EVENTS = (
  'customer.subscription.created',
  'customer.subscription.updated',
  'customer.subscription.deleted',
)


def get_subscription(company_id: int) -> CompanySubscription | None:
  with Session() as session:
    return session.query(CompanySubscription).filter_by(company_id=company_id).first()


def serialize_subscription(subscription: CompanySubscription | None) -> dict:
  if not subscription:
    return {'status': 'none', 'plan': None, 'active': False, 'current_period_end': None, 'cancel_at_period_end': False}

  return {
    'status': subscription.status,
    'plan': subscription.plan,
    'active': subscription.status in ACTIVE_STATUSES,
    'current_period_end': subscription.current_period_end.isoformat() if subscription.current_period_end else None,
    'cancel_at_period_end': subscription.cancel_at_period_end,
  }


def _get_or_create_subscription(company_id: int) -> CompanySubscription:
  return get_subscription(company_id) or create(CompanySubscription, {'company_id': company_id})


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


def _apply_subscription(company_id: int, stripe_subscription) -> None:
  update(_get_or_create_subscription(company_id), stripe_client.subscription_fields(stripe_subscription))


@subscription_bp.route('', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN], automatic_payment_required=True)
def get_company_subscription(_):
  return {
    'status': 'ok',
    'plans': public_plans(),
    'subscription': serialize_subscription(get_subscription(current_scope()['company_id'])),
  }


@subscription_bp.route('checkout', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN], automatic_payment_required=True)
def checkout(_):
  plan_id = (request.get_json(silent=True) or {}).get('plan')
  if plan_id not in PLANS:
    return {'status': 'ko', 'message': 'Piano non valido'}

  company_id = current_scope()['company_id']
  if serialize_subscription(get_subscription(company_id))['active']:
    return {'status': 'ko', 'message': 'Abbonamento già attivo: usa la gestione abbonamento per modificarlo'}

  customer_id = _get_or_create_customer(company_id)
  return {'status': 'ok', 'url': stripe_client.create_checkout_url(company_id, customer_id, plan_id)}


@subscription_bp.route('portal', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN], automatic_payment_required=True)
def portal(_):
  subscription = get_subscription(current_scope()['company_id'])
  if not subscription or not subscription.stripe_customer_id:
    return {'status': 'ko', 'message': 'Nessun abbonamento da gestire'}
  return {'status': 'ok', 'url': stripe_client.create_portal_url(subscription.stripe_customer_id)}


@subscription_bp.route('sync', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN], automatic_payment_required=True)
def sync(_):
  """Rilegge lo stato da Stripe. Al ritorno da Checkout il webhook può non
  essere ancora arrivato (o, in locale, non essere configurato): la pagina
  chiama questo per mostrare subito lo stato reale."""
  company_id = current_scope()['company_id']
  subscription = get_subscription(company_id)
  if subscription and subscription.stripe_customer_id:
    stripe_subscriptions = stripe_client.list_subscriptions(subscription.stripe_customer_id)
    if stripe_subscriptions:
      # Stripe le elenca dalla più recente: conta quella, anche dopo una
      # disdetta seguita da una nuova sottoscrizione.
      _apply_subscription(company_id, stripe_subscriptions[0])
  return {'status': 'ok', 'subscription': serialize_subscription(get_subscription(company_id))}


# Endpoint pubblico: l'unica autenticazione è la firma Stripe sul body grezzo.
@subscription_bp.route('webhook', methods=['POST'])
def webhook():
  try:
    event = stripe_client.construct_event(request.get_data(), request.headers.get('Stripe-Signature', ''))
  except Exception:
    return {'status': 'ko', 'message': 'Firma non valida'}, 400

  if event['type'] in WEBHOOK_SUBSCRIPTION_EVENTS:
    stripe_subscription = event['data']['object']
    company_id = (stripe_subscription.get('metadata') or {}).get('company_id')
    if company_id:
      _apply_subscription(int(company_id), stripe_subscription)

  return {'status': 'ok'}

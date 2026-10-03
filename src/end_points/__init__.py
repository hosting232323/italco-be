from functools import wraps
from flask import request

from api.users.auth import build_auth
from database_api import scope

from ..database.enum import UserRole
from ..database.queries import get_user_by_id_unscoped, is_rae_enabled, is_automatic_planning_enabled
from ..database.schema import User, UserSession


auth = build_auth(UserSession, get_user_by_id_unscoped, user_model=User)


def delivery_build_block_response(user: User):
  """Enforce configured platform-specific minimums on authenticated app calls."""
  if user.role != UserRole.DELIVERY:
    return None

  import src as app_module

  thresholds = {
    'ios': app_module.DELIVERY_APP_MIN_BUILD_NUMBER_IOS,
    'android': app_module.DELIVERY_APP_MIN_BUILD_NUMBER_ANDROID,
  }
  configured = {}
  for platform, raw in thresholds.items():
    try:
      configured[platform] = int(raw)
    except (TypeError, ValueError):
      continue
  if not configured:
    return None

  platform = request.headers.get('X-Delivery-Platform')
  raw_build = request.headers.get('X-Delivery-Build')
  if platform not in {'ios', 'android'} or not raw_build or not raw_build.isdigit():
    return {'status': 'update_required', 'message': 'Aggiorna l’app Delivery per continuare.'}, 426

  minimum = configured.get(platform)
  if minimum is not None and int(raw_build) < minimum:
    return {
      'status': 'update_required',
      'message': 'Aggiorna l’app Delivery per continuare.',
      'min_build_number': minimum,
    }, 426
  return None


def flask_session_authentication(
  roles: list[UserRole] = None,
  allow_query_token: bool = False,
  tenant_required: bool = True,
  rae_required: bool = False,
  automatic_planning_required: bool = False,
):
  """Autenticazione access/refresh e risoluzione del tenant attivo.

  Il ruolo dice cosa puoi fare, la company quali dati vedi: sono due assi
  distinti. Il super admin bypassa il primo e sceglie il secondo; tutti gli
  altri sono inchiodati alla propria company. Lo scope risolto qui è l'unica
  sorgente del filtro in lettura e del timbro in scrittura (database/events.py),
  ed è attivo solo per la durata della richiesta.

  rae_required=True marca gli endpoint che esistono solo se l'attività ha il
  modulo RAEE acceso. Nascondere le pagine nel frontend è cosmetica: il flag
  vale qualcosa solo se l'endpoint lo controlla da sé, e questo è il punto in
  cui la company attiva è già risolta per tutti i ruoli.

  automatic_planning_required=True fa lo stesso per la pianificazione automatica
  degli ordini: l'endpoint risponde ko se l'attività non ha il flag acceso.
  """

  def decorator(func):
    @wraps(func)
    def wrapper(user: User, *args, **kwargs):
      # Import locale: end_points.users importa questo modulo.
      from .users.session import get_token_company_id

      if roles and user.role != UserRole.SUPER_ADMIN and user.role not in roles:
        return {'status': 'forbidden', 'message': 'Ruolo non autorizzato'}, 403

      build_block = delivery_build_block_response(user)
      if build_block:
        return build_block

      company_id = get_token_company_id(allow_query_token) if user.role == UserRole.SUPER_ADMIN else user.company_id
      if tenant_required and not company_id:
        return {'status': 'forbidden', 'message': 'Nessuna company selezionata'}, 403

      if rae_required and not is_rae_enabled(company_id):
        return {'status': 'ko', 'message': 'Modulo RAEE non attivo per questa attività'}

      if automatic_planning_required and not is_automatic_planning_enabled(company_id):
        return {'status': 'ko', 'message': 'Pianificazione automatica non attiva per questa attività'}

      with scope(company_id=company_id):
        return func(user, *args, **kwargs)

    decorated = auth.authentication(allow_query_token=allow_query_token)(wrapper)
    # I test unitari esercitano la view nuda senza autenticazione.
    decorated.__wrapped__ = func
    return decorated

  return decorator

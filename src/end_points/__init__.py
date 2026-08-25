from functools import wraps
from database_api import scope
from api.users import build_session_authentication

from .. import STATIC_FOLDER
from ..database.enum import UserRole
from ..database.schema import User
from ..database.queries import get_user_by_nickname, is_rae_enabled


# refresh=False: il token lo riemettiamo qui sotto, perché quello della lib
# perderebbe il claim della company attiva a ogni risposta.
_session_authentication = build_session_authentication(
  STATIC_FOLDER,
  get_user_by_nickname,
  token_field='nickname',
  refresh=False,
)


def flask_session_authentication(
  roles: list[UserRole] = None,
  allow_query_token: bool = False,
  tenant_required: bool = True,
  rae_required: bool = False,
):
  """Autenticazione di sessione + risoluzione del tenant attivo.

  Il ruolo dice cosa puoi fare, la company quali dati vedi: sono due assi
  distinti. Il super admin bypassa il primo e sceglie il secondo; tutti gli
  altri sono inchiodati alla propria company. Lo scope risolto qui è l'unica
  sorgente del filtro in lettura e del timbro in scrittura (database/events.py),
  ed è attivo solo per la durata della richiesta.

  rae_required=True marca gli endpoint che esistono solo se l'attività ha il
  modulo RAEE acceso. Nascondere le pagine nel frontend è cosmetica: il flag
  vale qualcosa solo se l'endpoint lo controlla da sé, e questo è il punto in
  cui la company attiva è già risolta per tutti i ruoli.
  """

  def decorator(func):
    @wraps(func)
    def wrapper(user: User, *args, **kwargs):
      # Import locale: end_points.users importa questo modulo, quindi a livello
      # di modulo il ciclo non si chiuderebbe.
      from .users.session import create_jwt_token, get_token_company_id

      if roles and user.role != UserRole.SUPER_ADMIN and user.role not in roles:
        return {'status': 'ko', 'message': 'Ruolo non autorizzato'}

      if user.role == UserRole.SUPER_ADMIN:
        company_id = get_token_company_id(allow_query_token)
      else:
        company_id = user.company_id

      if tenant_required and not company_id:
        return {'status': 'ko', 'message': 'Nessuna company selezionata'}

      if rae_required and not is_rae_enabled(company_id):
        return {'status': 'ko', 'message': 'Modulo RAEE non attivo per questa attività'}

      with scope(company_id=company_id):
        result = func(user, *args, **kwargs)

      if isinstance(result, dict):
        # setdefault: /company/select riemette il token con la company appena
        # scelta, e non deve essere sovrascritto da quello dello scope precedente.
        result.setdefault('new_token', create_jwt_token(user, company_id))
      return result

    decorated = _session_authentication(allow_query_token=allow_query_token)(wrapper)
    # __wrapped__ punta alla view nuda, non al wrapper intermedio: i test che
    # esercitano la logica senza autenticazione la raggiungono da lì.
    decorated.__wrapped__ = func
    return decorated

  return decorator

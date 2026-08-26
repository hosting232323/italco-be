from sqlalchemy.orm import joinedload
from database_api import Session, scope, current_scope

from .schema import Company, User


def get_user_by_nickname(nickname: str) -> User | None:
  # Lookup di autenticazione, e unico punto in cui il nickname viene risolto:
  # deve vedere tutti gli utenti, super admin compreso, che per definizione non
  # appartiene ad alcuna company. Va quindi eseguito fuori scope.
  # joinedload: l'utente esce detached dalla sessione e la company va letta dopo.
  with scope(company_id=None), Session() as session:
    return session.query(User).options(joinedload(User.company)).filter(User.nickname == nickname).first()


def get_user_by_id_unscoped(user_id: int) -> User | None:
  """Lookup globale per access/refresh, indipendente dal tenant ambientale."""
  with scope(company_id=None), Session() as session:
    return session.query(User).options(joinedload(User.company)).filter(User.id == user_id).first()


def is_rae_enabled(company_id: int = None) -> bool:
  """Modulo RAEE dell'attività su cui si sta operando.

  company_id esplicito solo dove lo scope non è ancora aperto (il decoratore di
  sessione lo risolve prima di entrarci); altrove si legge dallo scope, così i
  controlli in profondità non devono trascinarsi il tenant lungo ogni firma.
  Senza company attiva non c'è modulo da accendere: False.
  """
  if company_id is None:
    company_id = current_scope().get('company_id')
  if not company_id:
    return False

  # Company non è un'entità con tenant, nessun filtro da schivare: la sessione
  # propria serve solo a non dipendere da quella del chiamante.
  with Session() as session:
    company: Company = session.get(Company, company_id)
    return bool(company and company.rae)

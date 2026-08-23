from sqlalchemy.orm import joinedload
from database_api import Session, scope

from .schema import User


def get_user_by_nickname(nickname: str) -> User | None:
  # Lookup di autenticazione, e unico punto in cui il nickname viene risolto:
  # deve vedere tutti gli utenti, super admin compreso, che per definizione non
  # appartiene ad alcuna company. Va quindi eseguito fuori scope.
  # joinedload: l'utente esce detached dalla sessione e la company va letta dopo.
  with scope(company_id=None), Session() as session:
    return session.query(User).options(joinedload(User.company)).filter(User.nickname == nickname).first()

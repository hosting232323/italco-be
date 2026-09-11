from contextlib import nullcontext

from sqlalchemy import desc

from database_api import Session, scope
from database_api.operations import create, delete, get_by_id, update

from ...database.schema import Company, RaeDisposalPlace


DELETE_LAST_PLACE_ERROR = "Non puoi eliminare l'ultimo luogo di smaltimento RAEE: il modulo RAEE è attivo"


def create_rae_disposal_place(company_id: int, data: dict):
  with scope(company_id=company_id):
    create(RaeDisposalPlace, data)
  return {'status': 'ok', 'message': 'Operazione completata!'}


def update_rae_disposal_place(company_id: int, id: int, data: dict):
  with scope(company_id=company_id):
    update(get_by_id(RaeDisposalPlace, id), data)
  return {'status': 'ok', 'message': 'Operazione completata!'}


def delete_rae_disposal_place(company_id: int, id: int):
  company = get_by_id(Company, company_id)
  if company and company.rae and count_rae_disposal_places(company_id) <= 1:
    return {'status': 'ko', 'message': DELETE_LAST_PLACE_ERROR}

  with scope(company_id=company_id):
    delete(get_by_id(RaeDisposalPlace, id))
  return {'status': 'ok', 'message': 'Operazione completata'}


def count_rae_disposal_places(company_id: int) -> int:
  with scope(company_id=company_id), Session() as session:
    return session.query(RaeDisposalPlace).count()


def get_rae_disposal_places(company_id: int = None) -> dict:
  """Lista dei luoghi di smaltimento.

  company_id esplicito serve alla gestione company del super admin, che opera
  su una company diversa da quella (se esiste) attiva nella sua sessione: lo
  scope qui sovrascrive quello ambientale solo per la durata della query. Senza
  company_id (rotta tenant) si usa lo scope già aperto dall'autenticazione.
  """
  with scope(company_id=company_id) if company_id else nullcontext():
    with Session() as session:
      places = session.query(RaeDisposalPlace).order_by(desc(RaeDisposalPlace.created_at)).all()

  return {'status': 'ok', 'rae_disposal_places': [place.to_dict() for place in places]}

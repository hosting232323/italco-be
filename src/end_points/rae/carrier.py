from database_api import Session
from ...database.schema import Carrier
from database_api.operations import create, delete, get_by_id, update


def create_rae_carrier(data: dict):
  create(Carrier, data)
  return {'status': 'ok', 'message': 'Operazione completata!'}


def update_rae_carrier(id: int, data: dict):
  update(get_by_id(Carrier, id), data)
  return {'status': 'ok', 'message': 'Operazione completata!'}


def delete_rae_carrier(id: int):
  delete(get_by_id(Carrier, id))
  return {'status': 'ok', 'message': 'Operazione completata'}


def get_rae_carriers():
  return {
    'status': 'ok',
    'rae_carriers': [rae_carrier.to_dict() for rae_carrier in query_rae_carriers()],
  }


def query_rae_carriers() -> list[Carrier]:
  with Session() as session:
    return session.query(Carrier).all()

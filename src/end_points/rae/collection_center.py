from database_api import Session
from ...database.schema import CollectionCenter
from database_api.operations import create, delete, get_by_id, update


def create_rae_collection_center(data: dict):
  create(CollectionCenter, data)
  return {'status': 'ok', 'message': 'Operazione completata!'}


def update_rae_collection_center(id: int, data: dict):
  update(get_by_id(CollectionCenter, id), data)
  return {'status': 'ok', 'message': 'Operazione completata!'}


def delete_rae_collection_center(id: int):
  delete(get_by_id(CollectionCenter, id))
  return {'status': 'ok', 'message': 'Operazione completata'}


def get_rae_collection_centers():
  return {
    'status': 'ok',
    'rae_collection_centers': [
      rae_collection_center.to_dict() for rae_collection_center in query_rae_collection_centers()
    ],
  }


def query_rae_collection_centers() -> list[CollectionCenter]:
  with Session() as session:
    return session.query(CollectionCenter).all()

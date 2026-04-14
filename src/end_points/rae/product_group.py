from database_api import Session
from ...database.schema import RaeProductGroup
from database_api.operations import create, delete, get_by_id, update


def create_rae_product_group(data: dict):
  rae_product_group: RaeProductGroup = create(RaeProductGroup, data)
  return {'status': 'ok', 'rae_product': rae_product_group.to_dict()}


def delete_rae_product_group(id: int):
  delete(get_by_id(RaeProductGroup, id))
  return {'status': 'ok', 'message': 'Operazione completata'}


def get_rae_product_groups():
  return {
    'status': 'ok',
    'rae_products': [rae_product_group.to_dict() for rae_product_group in query_rae_product_groups()],
  }


def update_rae_product_group(id: int, data: dict):
  rae_product_group: RaeProductGroup = update(get_by_id(RaeProductGroup, id), data)
  return {'status': 'ok', 'order': rae_product_group.to_dict()}


def query_rae_product_groups() -> list[RaeProductGroup]:
  with Session() as session:
    return session.query(RaeProductGroup).all()

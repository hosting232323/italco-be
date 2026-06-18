from database_api import Session
from database_api.operations import create, get_by_id, update
from ...database.schema import Disposal, Carrier, CollectionCenter


def create_rae_disposal(data: dict):
  create(Disposal, data)
  return {'status': 'ok', 'message': 'Operazione completata!'}


def update_rae_disposal(id: int, data: dict):
  update(get_by_id(Disposal, id), {'document_fir': data['document_fir']})
  return {'status': 'ok', 'message': 'Operazione completata!'}


def get_rae_disposals():
  rae_disposals = []
  for tupla in query_rae_disposals():
    rae_disposals = format_query_result(tupla, rae_disposals)
  return {'status': 'ok', 'rae_disposals': rae_disposals}


def format_query_result(tupla: tuple[Disposal, Carrier, CollectionCenter], list: list[dict]):
  for element in list:
    if element['id'] == tupla[0].id:
      return list

  output = {
    **tupla[0].to_dict(),
    'carrier': tupla[1].to_dict(),
    'collection_center': tupla[2].to_dict(),
  }
  list.append(output)
  return list


def query_rae_disposals() -> list[tuple[Disposal, Carrier, CollectionCenter]]:
  with Session() as session:
    return (
      session.query(Disposal, Carrier, CollectionCenter)
      .join(Carrier, Disposal.carrier_id == Carrier.id)
      .join(CollectionCenter, Disposal.collection_center_id == CollectionCenter.id)
      .all()
    )

from database_api import Session
from ...database.enum import RaeStatus
from sqlalchemy.orm import Session as session_type
from database_api.operations import create, get_by_id, get_by_ids, update
from ...database.schema import Disposal, Carrier, CollectionCenter, RaeProduct, RaeProductGroup


def create_rae_disposal(data: dict):
  rae_product_ids = data.pop('rae_product_ids', [])
  disposal = create(Disposal, data)
  for rp in get_by_ids(RaeProduct, rae_product_ids):
    update(rp, {'disposal_id': disposal.id, 'status': RaeStatus.DISPOSED_OFF})
  return {'status': 'ok', 'message': 'Operazione completata!'}


def update_rae_disposal(id: int, data: dict, session: session_type):
  update_data = {}
  if 'weight' in data:
    update_data['weight'] = data['weight']
  if 'first_copy_document_fir' in data:
    update_data['first_copy_document_fir'] = data['first_copy_document_fir']
  if 'fourth_copy_document_fir' in data:
    update_data['fourth_copy_document_fir'] = data['fourth_copy_document_fir']
  if update_data:
    update(get_by_id(Disposal, id), update_data, session=session)
  return {'status': 'ok', 'message': 'Operazione completata!'}


def get_rae_disposals():
  rae_disposals = []
  for row in query_rae_disposals():
    rae_disposals = format_query_result(row, rae_disposals)
  return {'status': 'ok', 'rae_disposals': rae_disposals}


def format_query_result(tupla: tuple[Disposal, Carrier, CollectionCenter, str | None, int | None], list: list[dict]):
  for element in list:
    if element['id'] == tupla[0].id:
      if tupla[3] is not None:
        groups = element['group_quantities']
        groups[tupla[3]] = groups.get(tupla[3], 0) + tupla[4]
        element['group_quantities'] = dict(sorted(groups.items()))
      return list

  output = {
    **tupla[0].to_dict(),
    'carrier': tupla[1].to_dict(),
    'collection_center': tupla[2].to_dict(),
    'group_quantities': {},
  }
  if tupla[3] is not None:
    output['group_quantities'][tupla[3]] = tupla[4]
  list.append(output)
  return list


def query_rae_disposals(
  disposal_id: int = None,
) -> list[tuple[Disposal, Carrier, CollectionCenter, str | None, int | None]]:
  with Session() as session:
    query = (
      session.query(
        Disposal,
        Carrier,
        CollectionCenter,
        RaeProductGroup.group_code,
        RaeProduct.quantity,
      )
      .join(Carrier, Disposal.carrier_id == Carrier.id)
      .join(CollectionCenter, Disposal.collection_center_id == CollectionCenter.id)
      .outerjoin(RaeProduct, Disposal.id == RaeProduct.disposal_id)
      .outerjoin(RaeProductGroup, RaeProduct.rae_product_group_id == RaeProductGroup.id)
    )
    if disposal_id is not None:
      query = query.filter(Disposal.id == disposal_id)
    return query.all()

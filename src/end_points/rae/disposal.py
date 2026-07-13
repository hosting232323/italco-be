from database_api import Session
from ...database.enum import RaeStatus
from sqlalchemy import func
from sqlalchemy.orm import Session as session_type
from database_api.operations import create, get_by_id, get_by_ids, update
from ...database.schema import Disposal, Carrier, CollectionCenter, RaeProduct, RaeProductGroup
from .product_group import group_quantities_by_disposal


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
  rows = query_rae_disposals()
  rae_disposals = []
  for disposal, carrier, collection_center, _group_code, _quantity in rows:
    rae_disposals = format_query_result((disposal, carrier, collection_center), rae_disposals)

  quantities_by_disposal = group_quantities_by_disposal(
    (disposal.id, group_code, quantity)
    for disposal, _carrier, _collection_center, group_code, quantity in rows
    if group_code is not None
  )
  for disposal in rae_disposals:
    disposal['group_quantities'] = quantities_by_disposal.get(disposal['id'], {})

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


def query_rae_disposals() -> list[tuple[Disposal, Carrier, CollectionCenter, str | None, int]]:
  with Session() as session:
    return (
      session.query(
        Disposal,
        Carrier,
        CollectionCenter,
        RaeProductGroup.group_code,
        func.sum(RaeProduct.quantity),
      )
      .join(Carrier, Disposal.carrier_id == Carrier.id)
      .join(CollectionCenter, Disposal.collection_center_id == CollectionCenter.id)
      .outerjoin(RaeProduct, Disposal.id == RaeProduct.disposal_id)
      .outerjoin(RaeProductGroup, RaeProduct.rae_product_group_id == RaeProductGroup.id)
      .group_by(Disposal.id, Carrier.id, CollectionCenter.id, RaeProductGroup.group_code)
      .all()
    )

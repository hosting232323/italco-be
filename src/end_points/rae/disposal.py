from sqlalchemy import desc

from database_api import Session
from ...database.enum import RaeStatus
from sqlalchemy.orm import Session as session_type
from database_api.operations import create, get_by_ids, update, get_by_id
from ...database.schema import Disposal, Carrier, CollectionCenter, RaeProduct, DisposalDocument


def get_disposal_document(disposal_id: int) -> DisposalDocument:
  with Session() as session:
    return (
      session.query(DisposalDocument)
      .filter(DisposalDocument.disposal_id == disposal_id)
      .order_by(desc(DisposalDocument.created_at))
      .first()
    )


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
  for tupla in query_rae_disposals():
    rae_disposals = format_query_result(tupla, rae_disposals)
  return {'status': 'ok', 'rae_disposals': rae_disposals}


def format_query_result(tupla: tuple[Disposal, Carrier, CollectionCenter], list: list[dict]):
  for element in list:
    if element['id'] == tupla[0].id:
      return list

  document = get_disposal_document(tupla[0].id)
  output = {
    **tupla[0].to_dict(),
    'document_fir': document.link if document else None,
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

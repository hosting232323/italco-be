from sqlalchemy import desc

from database_api import Session
from ...database.enum import RaeStatus
from sqlalchemy.orm import Session as session_type
from database_api.operations import create, get_by_ids, update, get_by_id
from ...database.schema import (
  Disposal,
  Carrier,
  CollectionCenter,
  RaeProduct,
  DisposalFirstCopyDocument,
  DisposalFourthCopyDocument,
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
  if update_data:
    update(get_by_id(Disposal, id), update_data, session=session)

  if 'first_copy_document_fir' in data:
    create(
      DisposalFirstCopyDocument,
      {'disposal_id': id, 'link': data['first_copy_document_fir']},
      session=session,
    )
  if 'fourth_copy_document_fir' in data:
    create(
      DisposalFourthCopyDocument,
      {'disposal_id': id, 'link': data['fourth_copy_document_fir']},
      session=session,
    )
  return {'status': 'ok', 'message': 'Operazione completata!'}


def get_rae_disposals():
  with Session() as session:
    results = (
      session.query(Disposal, Carrier, CollectionCenter)
      .join(Carrier, Disposal.carrier_id == Carrier.id)
      .join(CollectionCenter, Disposal.collection_center_id == CollectionCenter.id)
      .all()
    )

    rae_disposals = []
    for disposal, carrier, collection_center in results:
      first_copy = (
        session.query(DisposalFirstCopyDocument)
        .filter(DisposalFirstCopyDocument.disposal_id == disposal.id)
        .order_by(desc(DisposalFirstCopyDocument.created_at))
        .first()
      )
      fourth_copy = (
        session.query(DisposalFourthCopyDocument)
        .filter(DisposalFourthCopyDocument.disposal_id == disposal.id)
        .order_by(desc(DisposalFourthCopyDocument.created_at))
        .first()
      )

      output = {
        **disposal.to_dict(),
        'first_copy_document_fir': first_copy.link if first_copy else None,
        'fourth_copy_document_fir': fourth_copy.link if fourth_copy else None,
        'carrier': carrier.to_dict(),
        'collection_center': collection_center.to_dict(),
      }
      rae_disposals.append(output)

    return {'status': 'ok', 'rae_disposals': rae_disposals}

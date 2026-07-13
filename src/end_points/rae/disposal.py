from sqlalchemy import desc

from database_api import Session
from ...database.enum import RaeStatus
from database_api.operations import create, get_by_ids, update, get_by_id

from ...utils.storage import SessionWithStorage
from .document import handle_document_by_name
from ...database.schema import (
  Disposal,
  Carrier,
  CollectionCenter,
  RaeProduct,
  FirFirstDocument,
  FirFourthDocument,
)


def create_rae_disposal(data: dict):
  rae_product_ids = data.pop('rae_product_ids', [])
  disposal = create(Disposal, data)
  for rp in get_by_ids(RaeProduct, rae_product_ids):
    update(rp, {'disposal_id': disposal.id, 'status': RaeStatus.DISPOSED_OFF})
  return {'status': 'ok', 'message': 'Operazione completata!'}


def ensure_document_not_already_stored(model, disposal_id: int, uploaded_file, session):
  if uploaded_file and session.query(model.id).filter(model.disposal_id == disposal_id).first():
    raise ValueError(f'{model.__name__} già presente per lo smaltimento {disposal_id}')


def update_rae_disposal(id: int, data: dict, files):
  with SessionWithStorage() as session:
    ensure_document_not_already_stored(
      FirFirstDocument,
      id,
      files.get('first_copy_document_fir'),
      session,
    )
    ensure_document_not_already_stored(
      FirFourthDocument,
      id,
      files.get('fourth_copy_document_fir'),
      session,
    )
    data = handle_document_by_name(
      data,
      'rae/fir-first-document',
      'fir_first_document',
      'first_copy_document_fir',
      uploaded_file=files.get('first_copy_document_fir'),
      session=session,
      storage=session,
    )
    data = handle_document_by_name(
      data,
      'rae/fir-fourth-document',
      'fir_fourth_document',
      'fourth_copy_document_fir',
      uploaded_file=files.get('fourth_copy_document_fir'),
      session=session,
      storage=session,
    )

    update_data = {}
    if 'weight' in data:
      update_data['weight'] = data['weight']
    if update_data:
      update(get_by_id(Disposal, id, session=session), update_data, session=session)

    if 'first_copy_document_fir' in data:
      create(
        FirFirstDocument,
        {'disposal_id': id, 'link': data['first_copy_document_fir']},
        session=session,
      )
    if 'fourth_copy_document_fir' in data:
      create(
        FirFourthDocument,
        {'disposal_id': id, 'link': data['fourth_copy_document_fir']},
        session=session,
      )
    session.commit()

  return {'status': 'ok', 'message': 'Operazione completata!'}


def get_rae_disposals():
  rae_disposals = []
  for result in query_rae_disposals():
    rae_disposals = format_query_result(result, rae_disposals)
  return {'status': 'ok', 'rae_disposals': rae_disposals}


def query_rae_disposals():
  with Session() as session:
    return (
      session.query(
        Disposal,
        Carrier,
        CollectionCenter,
        FirFirstDocument,
        FirFourthDocument,
      )
      .join(Carrier, Disposal.carrier_id == Carrier.id)
      .join(CollectionCenter, Disposal.collection_center_id == CollectionCenter.id)
      .outerjoin(FirFirstDocument, FirFirstDocument.disposal_id == Disposal.id)
      .outerjoin(FirFourthDocument, FirFourthDocument.disposal_id == Disposal.id)
      .order_by(
        Disposal.id,
        desc(FirFirstDocument.created_at).nullslast(),
        desc(FirFourthDocument.created_at).nullslast(),
      )
      .all()
    )


def format_query_result(
  result: tuple[Disposal, Carrier, CollectionCenter, FirFirstDocument | None, FirFourthDocument | None],
  rae_disposals: list[dict],
):
  disposal, carrier, collection_center, fir_first, fir_fourth = result
  if any(element['id'] == disposal.id for element in rae_disposals):
    return rae_disposals

  rae_disposals.append(
    {
      **disposal.to_dict(),
      'first_copy_document_fir': fir_first.link if fir_first else None,
      'fourth_copy_document_fir': fir_fourth.link if fir_fourth else None,
      'carrier': carrier.to_dict(),
      'collection_center': collection_center.to_dict(),
    }
  )
  return rae_disposals

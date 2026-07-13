from database_api import Session
from database_api.operations import create, get_by_id, get_by_ids, update

from ...database.enum import RaeStatus
from ...database.schema import (
  Carrier,
  CollectionCenter,
  Disposal,
  FirFirstDocument,
  FirFourthDocument,
  RaeProduct,
  RaeProductGroup,
)
from ...utils.storage import SessionWithStorage
from .document import handle_document_by_name


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
    ensure_document_not_already_stored(FirFirstDocument, id, files.get('first_copy_document_fir'), session)
    ensure_document_not_already_stored(FirFourthDocument, id, files.get('fourth_copy_document_fir'), session)
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
  for row in query_rae_disposals():
    rae_disposals = format_query_result(row, rae_disposals)
  return {'status': 'ok', 'rae_disposals': rae_disposals}


def format_query_result(
  row: tuple[
    Disposal,
    Carrier,
    CollectionCenter,
    FirFirstDocument | None,
    FirFourthDocument | None,
    str | None,
    int | None,
  ],
  rae_disposals: list[dict],
):
  disposal, carrier, collection_center, fir_first, fir_fourth, group_code, quantity = row
  for element in rae_disposals:
    if element['id'] == disposal.id:
      if group_code is not None:
        groups = element['group_quantities']
        groups[group_code] = groups.get(group_code, 0) + (quantity or 0)
        element['group_quantities'] = dict(sorted(groups.items()))
      return rae_disposals

  output = {
    **disposal.to_dict(),
    'first_copy_document_fir': fir_first.link if fir_first else None,
    'fourth_copy_document_fir': fir_fourth.link if fir_fourth else None,
    'carrier': carrier.to_dict(),
    'collection_center': collection_center.to_dict(),
    'group_quantities': {},
  }
  if group_code is not None:
    output['group_quantities'][group_code] = quantity or 0
  rae_disposals.append(output)
  return rae_disposals


def query_rae_disposals(
  disposal_id: int = None,
) -> list[
  tuple[
    Disposal,
    Carrier,
    CollectionCenter,
    FirFirstDocument | None,
    FirFourthDocument | None,
    str | None,
    int | None,
  ]
]:
  with Session() as session:
    query = (
      session.query(
        Disposal,
        Carrier,
        CollectionCenter,
        FirFirstDocument,
        FirFourthDocument,
        RaeProductGroup.group_code,
        RaeProduct.quantity,
      )
      .join(Carrier, Disposal.carrier_id == Carrier.id)
      .join(CollectionCenter, Disposal.collection_center_id == CollectionCenter.id)
      .outerjoin(FirFirstDocument, FirFirstDocument.disposal_id == Disposal.id)
      .outerjoin(FirFourthDocument, FirFourthDocument.disposal_id == Disposal.id)
      .outerjoin(RaeProduct, Disposal.id == RaeProduct.disposal_id)
      .outerjoin(RaeProductGroup, RaeProduct.rae_product_group_id == RaeProductGroup.id)
    )
    if disposal_id is not None:
      query = query.filter(Disposal.id == disposal_id)
    return query.all()

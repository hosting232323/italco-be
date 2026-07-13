from io import BytesIO

import pytest
from database_api import Session
from database_api.operations import create
from werkzeug.datastructures import FileStorage

from src.database.schema import Carrier, CollectionCenter, Disposal, FirFirstDocument, FirFourthDocument
from src.end_points.rae.disposal import get_rae_disposals, update_rae_disposal
from src.utils.storage import SessionWithStorage


def pdf_file(filename: str) -> FileStorage:
  return FileStorage(stream=BytesIO(b'%PDF-1.4\n%%EOF\n'), filename=filename, content_type='application/pdf')


def create_disposal(session):
  carrier = create(Carrier, {'company_name': 'Carrier'}, session=session)
  center = create(CollectionCenter, {'company_name': 'Center'}, session=session)
  return create(
    Disposal,
    {'carrier_id': carrier.id, 'collection_center_id': center.id},
    session=session,
  )


def test_get_rae_disposals_joins_documents_and_keeps_disposals_without_files(seeded_db):
  with Session() as session:
    disposal = create_disposal(session)
    disposal_without_files = create_disposal(session)
    session.add_all(
      [
        FirFirstDocument(link='first.pdf', disposal_id=disposal.id),
        FirFourthDocument(link='fourth.pdf', disposal_id=disposal.id),
      ]
    )
    session.commit()
    disposal_id = disposal.id
    disposal_without_files_id = disposal_without_files.id

  response = get_rae_disposals()
  disposals = {item['id']: item for item in response['rae_disposals']}

  assert response['status'] == 'ok'
  assert disposals[disposal_id]['first_copy_document_fir'] == 'first.pdf'
  assert disposals[disposal_id]['fourth_copy_document_fir'] == 'fourth.pdf'
  assert disposals[disposal_id]['carrier']['company_name'] == 'Carrier'
  assert disposals[disposal_id]['collection_center']['company_name'] == 'Center'
  assert disposals[disposal_without_files_id]['first_copy_document_fir'] is None
  assert disposals[disposal_without_files_id]['fourth_copy_document_fir'] is None


@pytest.mark.parametrize(
  ('model', 'file_field'),
  [
    (FirFirstDocument, 'first_copy_document_fir'),
    (FirFourthDocument, 'fourth_copy_document_fir'),
  ],
)
def test_update_disposal_rejects_replacing_an_existing_document(
  seeded_db,
  monkeypatch,
  model,
  file_field,
):
  with Session() as session:
    disposal = create_disposal(session)
    create(model, {'link': 'already-stored.pdf', 'disposal_id': disposal.id}, session=session)
    session.commit()
    disposal_id = disposal.id

  upload_called = False

  def unexpected_upload(*args, **kwargs):
    nonlocal upload_called
    upload_called = True
    raise AssertionError('storage must not be called')

  monkeypatch.setattr(SessionWithStorage, 'upload', unexpected_upload)

  with pytest.raises(ValueError, match='già presente'):
    update_rae_disposal(disposal_id, {}, {file_field: pdf_file('replacement.pdf')})

  assert upload_called is False
  with Session() as session:
    documents = session.query(model).filter(model.disposal_id == disposal_id).all()
    assert [document.link for document in documents] == ['already-stored.pdf']

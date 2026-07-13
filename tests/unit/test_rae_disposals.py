from datetime import datetime, timezone

from database_api import Session
from database_api.operations import create

from src.database.schema import Carrier, CollectionCenter, Disposal, FirFirstDocument, FirFourthDocument
from src.end_points.rae.disposal import get_rae_disposals


def test_get_rae_disposals_joins_latest_documents_and_keeps_disposals_without_files(seeded_db):
  older = datetime(2026, 7, 1, tzinfo=timezone.utc)
  newer = datetime(2026, 7, 2, tzinfo=timezone.utc)

  with Session() as session:
    carrier = create(Carrier, {'company_name': 'Carrier'}, session=session)
    center = create(CollectionCenter, {'company_name': 'Center'}, session=session)
    disposal = create(
      Disposal,
      {'carrier_id': carrier.id, 'collection_center_id': center.id},
      session=session,
    )
    disposal_without_files = create(
      Disposal,
      {'carrier_id': carrier.id, 'collection_center_id': center.id},
      session=session,
    )
    session.add_all(
      [
        FirFirstDocument(link='first-old.pdf', disposal_id=disposal.id, created_at=older),
        FirFirstDocument(link='first-new.pdf', disposal_id=disposal.id, created_at=newer),
        FirFourthDocument(link='fourth-old.pdf', disposal_id=disposal.id, created_at=older),
        FirFourthDocument(link='fourth-new.pdf', disposal_id=disposal.id, created_at=newer),
      ]
    )
    session.commit()
    disposal_id = disposal.id
    disposal_without_files_id = disposal_without_files.id

  response = get_rae_disposals()
  disposals = {item['id']: item for item in response['rae_disposals']}

  assert response['status'] == 'ok'
  assert disposals[disposal_id]['first_copy_document_fir'] == 'first-new.pdf'
  assert disposals[disposal_id]['fourth_copy_document_fir'] == 'fourth-new.pdf'
  assert disposals[disposal_id]['carrier']['company_name'] == 'Carrier'
  assert disposals[disposal_id]['collection_center']['company_name'] == 'Center'
  assert disposals[disposal_without_files_id]['first_copy_document_fir'] is None
  assert disposals[disposal_without_files_id]['fourth_copy_document_fir'] is None

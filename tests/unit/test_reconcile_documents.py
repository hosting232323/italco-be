import os
from datetime import datetime

from api.storage import get_full_path
from database_api import Session
from database_api.operations import create

from scripts.reconcile_documents import reconcile
from src.database.schema import Carrier, CollectionCenter, Disposal, FirFirstDocument


FAKE_PDF = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog >>
endobj
trailer
<< /Root 1 0 R >>
%%EOF
"""


def test_reconcile_documents_with_real_fake_pdf_files(seeded_db, tmp_path):
  config = {
    'model': FirFirstDocument,
    'owner_field': 'disposal_id',
    'subfolder': 'fir-first-document',
    'label': 'First Copy FIR',
    'owner_required': True,
  }
  prefix = 'https://files.example.test/rae/fir-first-document/'

  with Session() as session:
    carrier = create(Carrier, {}, session=session)
    center = create(CollectionCenter, {}, session=session)
    disposal = create(
      Disposal,
      {'carrier_id': carrier.id, 'collection_center_id': center.id},
      session=session,
    )
    session.add_all(
      [
        FirFirstDocument(link=prefix + 'linked.pdf', disposal_id=disposal.id),
        FirFirstDocument(link=prefix + 'missing.pdf', disposal_id=disposal.id),
      ]
    )
    session.commit()
    disposal_id = disposal.id

  storage_folder = get_full_path(str(tmp_path), config['subfolder'], False)
  os.makedirs(storage_folder, exist_ok=True)
  linked_path = os.path.join(storage_folder, 'linked.pdf')
  orphan_path = os.path.join(storage_folder, 'orphan.pdf')
  unowned_path = os.path.join(storage_folder, 'unowned.pdf')
  for path in (linked_path, orphan_path, unowned_path):
    with open(path, 'wb') as file:
      file.write(FAKE_PDF)

  expected_mtime = datetime(2026, 7, 10, 12, 30).astimezone().timestamp()
  os.utime(orphan_path, (expected_mtime, expected_mtime))
  known_owners = {'fir_first_document': {'orphan.pdf': disposal_id}}

  preview = reconcile(config, static_folder=str(tmp_path), known_owners=known_owners, apply=False)
  assert preview['orphans'] == ['orphan.pdf', 'unowned.pdf']
  assert preview['missing'] == ['missing.pdf']
  assert preview['imported'] == []
  assert preview['unresolved'] == ['unowned.pdf']

  with Session() as session:
    assert session.query(FirFirstDocument).count() == 2

  applied = reconcile(config, static_folder=str(tmp_path), known_owners=known_owners, apply=True)
  assert applied['imported'] == ['orphan.pdf']
  assert applied['unresolved'] == ['unowned.pdf']

  with Session() as session:
    imported = session.query(FirFirstDocument).filter(FirFirstDocument.link == prefix + 'orphan.pdf').one()
    assert imported.disposal_id == disposal_id
    assert abs(imported.created_at.timestamp() - expected_mtime) < 1

  repeated = reconcile(config, static_folder=str(tmp_path), known_owners=known_owners, apply=True)
  assert repeated['orphans'] == ['unowned.pdf']
  assert repeated['imported'] == []
  assert repeated['unresolved'] == ['unowned.pdf']

  with Session() as session:
    assert session.query(FirFirstDocument).count() == 3

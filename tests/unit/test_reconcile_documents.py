import os
from datetime import datetime

from database_api import Session

from scripts.reconcile_documents import reconcile
from src.database.schema import DisposalFirstCopyDocument
from api.storage import get_full_path


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
    'model': DisposalFirstCopyDocument,
    'owner_field': 'disposal_id',
    'subfolder': 'first-copy-fir-documents',
    'label': 'First Copy FIR',
  }
  prefix = 'https://files.example.test/rae/first-copy-fir-documents/'

  with Session() as session:
    session.add_all(
      [
        DisposalFirstCopyDocument(link=prefix + 'linked.pdf'),
        DisposalFirstCopyDocument(link=prefix + 'missing.pdf'),
      ]
    )
    session.commit()

  storage_folder = get_full_path(str(tmp_path), config['subfolder'], False)
  os.makedirs(storage_folder, exist_ok=True)
  linked_path = os.path.join(storage_folder, 'linked.pdf')
  orphan_path = os.path.join(storage_folder, 'orphan.pdf')
  with open(linked_path, 'wb') as file:
    file.write(FAKE_PDF)
  with open(orphan_path, 'wb') as file:
    file.write(FAKE_PDF)

  expected_mtime = datetime(2026, 7, 10, 12, 30).astimezone().timestamp()
  os.utime(orphan_path, (expected_mtime, expected_mtime))

  preview = reconcile(config, static_folder=str(tmp_path), known_owners={}, apply=False)
  assert preview['orphans'] == ['orphan.pdf']
  assert preview['missing'] == ['missing.pdf']
  assert preview['imported'] == []

  with Session() as session:
    assert session.query(DisposalFirstCopyDocument).count() == 2

  applied = reconcile(config, static_folder=str(tmp_path), known_owners={}, apply=True)
  assert applied['imported'] == ['orphan.pdf']

  with Session() as session:
    imported = (
      session.query(DisposalFirstCopyDocument).filter(DisposalFirstCopyDocument.link == prefix + 'orphan.pdf').one()
    )
    assert imported.disposal_id is None
    assert abs(imported.created_at.timestamp() - expected_mtime) < 1

  repeated = reconcile(config, static_folder=str(tmp_path), known_owners={}, apply=True)
  assert repeated['orphans'] == []
  assert repeated['imported'] == []

  with Session() as session:
    assert session.query(DisposalFirstCopyDocument).count() == 3

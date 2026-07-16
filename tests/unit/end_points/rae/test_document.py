from io import BytesIO

from werkzeug.datastructures import FileStorage

from database_api import Session

from src.database.schema import DtrDocument
from src.end_points.rae.document import handle_document_by_name, store_document
from src.utils.storage import SessionWithStorage

from tests.unit.factories import create_order, create_rae_product, create_user
from src.database.enum import UserRole


FAKE_PDF = b'%PDF-1.4\n%%EOF\n'


def _pdf(filename='doc.pdf', content_type='application/pdf'):
  return FileStorage(stream=BytesIO(FAKE_PDF), filename=filename, content_type=content_type)


def _fake_upload(monkeypatch):
  import src.utils.storage as storage_module

  monkeypatch.setattr(storage_module, 'upload_file', lambda content, filename, folder, **kwargs: f'/fake/{filename}')


def test_store_document_creates_row_with_sequence_id(app, db, monkeypatch):
  _fake_upload(monkeypatch)
  customer = create_user(UserRole.CUSTOMER)
  rae_product = create_rae_product(create_order(), customer)

  with app.test_request_context():
    with SessionWithStorage() as session:
      document = store_document(
        DtrDocument,
        'rae_product_id',
        rae_product.id,
        'rae/dtr-documents',
        uploaded_file=_pdf(),
        session=session,
        storage=session,
      )
      session.commit()
      document_id = document.id

  with Session() as session:
    stored = session.get(DtrDocument, document_id)
    assert stored.rae_product_id == rae_product.id
    assert stored.link.endswith(f'{document_id}.pdf')
    assert '/rae/dtr-documents/' in stored.link


def test_store_document_ignores_missing_or_non_pdf(app, db):
  with app.test_request_context():
    with SessionWithStorage() as session:
      assert store_document(DtrDocument, 'rae_product_id', 1, 'rae/dtr-documents', None, session, session) is None
      assert (
        store_document(
          DtrDocument,
          'rae_product_id',
          1,
          'rae/dtr-documents',
          _pdf(content_type='image/png'),
          session,
          session,
        )
        is None
      )

  with Session() as session:
    assert session.query(DtrDocument).count() == 0


def test_handle_document_by_name_sets_field(app, db, monkeypatch):
  _fake_upload(monkeypatch)

  with app.test_request_context():
    with SessionWithStorage() as session:
      data = handle_document_by_name(
        {'weight': 10},
        'rae/fir-first-document',
        'fir_first_document',
        'first_copy_document_fir',
        uploaded_file=_pdf(),
        session=session,
        storage=session,
      )

  assert data['weight'] == 10
  assert '/rae/fir-first-document/' in data['first_copy_document_fir']


def test_handle_document_by_name_without_file_returns_data_unchanged(app, db):
  with app.test_request_context():
    with SessionWithStorage() as session:
      data = handle_document_by_name(
        {'weight': 10},
        'rae/fir-first-document',
        'fir_first_document',
        'first_copy_document_fir',
        uploaded_file=None,
        session=session,
        storage=session,
      )

  assert data == {'weight': 10}

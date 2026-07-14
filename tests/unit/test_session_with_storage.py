from io import BytesIO
import os

import pytest
from api.storage import get_full_path
from database_api import Session
from database_api.operations import create
from flask import Flask
from sqlalchemy.exc import IntegrityError
from werkzeug.datastructures import FileStorage

from src.database.enum import RaeStatus, UserRole
from src.database.schema import (
  FirFirstDocument,
  FirFourthDocument,
  Order,
  DtrDocument,
  RaeProduct,
  RaeProductGroup,
  User,
)
from src.end_points.rae import rae_bp
from src.utils import storage as storage_module
from src.utils.storage import SessionWithStorage
from tests.utils import auth_header_for


FAKE_PDF = b'%PDF-1.4\n%%EOF\n'


def pdf_file(filename: str) -> FileStorage:
  return FileStorage(stream=BytesIO(FAKE_PDF), filename=filename, content_type='application/pdf')


def test_partial_upload_is_removed(monkeypatch, tmp_path):
  expected_path = get_full_path(str(tmp_path), 'documents', filename='partial.pdf')

  def fail_after_partial_write(content, filename, folder, *, server=None, subfolder=None, ignore_dev=None):
    path = get_full_path(folder, subfolder, ignore_dev, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as file:
      file.write(b'partial')
    raise OSError('upload interrupted')

  monkeypatch.setattr(storage_module, 'upload_file', fail_after_partial_write)

  with pytest.raises(OSError, match='upload interrupted'):
    with SessionWithStorage() as storage:
      storage.upload(pdf_file('partial.pdf'), 'partial.pdf', str(tmp_path), subfolder='documents')

  assert not os.path.exists(expected_path)


def test_multiple_uploaded_files_are_removed_together(tmp_path):
  filenames = ['first.pdf', 'second.pdf']
  paths = [get_full_path(str(tmp_path), 'documents', filename=filename) for filename in filenames]

  with pytest.raises(RuntimeError, match='database failure'):
    with SessionWithStorage() as storage:
      for filename in filenames:
        storage.upload(pdf_file(filename), filename, str(tmp_path), subfolder='documents')
      raise RuntimeError('database failure')

  assert all(not os.path.exists(path) for path in paths)


def test_document_models_use_the_new_table_names():
  assert DtrDocument.__tablename__ == 'dtr_document'
  assert FirFirstDocument.__tablename__ == 'fir_first_document'
  assert FirFourthDocument.__tablename__ == 'fir_fourth_document'
  assert FirFirstDocument.__table__.c.disposal_id.nullable is False
  assert FirFourthDocument.__table__.c.disposal_id.nullable is False
  assert FirFirstDocument.__table__.c.disposal_id.unique is True
  assert FirFourthDocument.__table__.c.disposal_id.unique is True


def test_storage_and_database_are_committed_together(seeded_db, tmp_path):
  with SessionWithStorage() as session:
    stored_path = session.upload(pdf_file('committed.pdf'), 'committed.pdf', str(tmp_path), subfolder='documents')
    create(DtrDocument, {'link': stored_path}, session=session)
    session.commit()

  assert os.path.isfile(get_full_path(str(tmp_path), 'documents', filename='committed.pdf'))
  with Session() as session:
    assert session.query(DtrDocument).filter_by(link=stored_path).count() == 1


def test_database_failure_rolls_back_file_and_row(seeded_db, tmp_path):
  stored_path = get_full_path(str(tmp_path), 'documents', filename='rolled-back.pdf')

  with pytest.raises(IntegrityError):
    with SessionWithStorage() as session:
      session.upload(pdf_file('rolled-back.pdf'), 'rolled-back.pdf', str(tmp_path), subfolder='documents')
      create(
        FirFirstDocument,
        {'link': stored_path, 'disposal_id': 999_999_999},
        session=session,
      )
      session.commit()

  assert not os.path.exists(stored_path)
  with Session() as session:
    assert session.query(FirFirstDocument).filter_by(link=stored_path).count() == 0


def test_session_without_commit_rolls_back_storage_and_database(seeded_db, tmp_path):
  stored_path = get_full_path(str(tmp_path), 'documents', filename='not-committed.pdf')

  with SessionWithStorage() as session:
    session.upload(pdf_file('not-committed.pdf'), 'not-committed.pdf', str(tmp_path), subfolder='documents')
    create(DtrDocument, {'link': stored_path}, session=session)

  assert not os.path.exists(stored_path)
  with Session() as session:
    assert session.query(DtrDocument).filter_by(link=stored_path).count() == 0


def test_rae_endpoint_returns_ko_when_storage_upload_fails(seeded_db, monkeypatch):
  with Session() as session:
    user = session.query(User).first()
    order = session.query(Order).first()
    group = create(
      RaeProductGroup,
      {'name': 'Test RAE', 'cer_code': 123456, 'group_code': 'R1'},
      session=session,
    )
    product = create(
      RaeProduct,
      {
        'user_id': user.id,
        'order_id': order.id,
        'rae_product_group_id': group.id,
        'status': RaeStatus.GENERATED,
      },
      session=session,
    )
    session.commit()
    product_id = product.id
    status = product.status.value
    document_count = session.query(DtrDocument).filter_by(rae_product_id=product_id).count()

  def fail_upload(*args, **kwargs):
    raise OSError('storage unavailable')

  monkeypatch.setattr(SessionWithStorage, 'upload', fail_upload)

  app = Flask(__name__)

  @app.errorhandler(Exception)
  def handle_exception(_):
    return {'status': 'ko', 'message': 'Errore generico'}

  app.register_blueprint(rae_bp, url_prefix='/rae/')
  client = app.test_client()
  response = client.put(
    f'/rae/product/{product_id}',
    data={
      'data': f'{{"status": "{status}"}}',
      'document': (BytesIO(FAKE_PDF), 'document.pdf', 'application/pdf'),
    },
    headers=auth_header_for('admin', role=UserRole.ADMIN),
  )

  assert response.status_code == 200
  assert response.get_json()['status'] == 'ko'
  with Session() as session:
    assert session.query(DtrDocument).filter_by(rae_product_id=product_id).count() == document_count

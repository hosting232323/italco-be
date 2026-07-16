import os
from io import BytesIO

import pytest
from api.storage import get_full_path
from database_api import Session
from database_api.operations import create
from sqlalchemy.exc import IntegrityError
from werkzeug.datastructures import FileStorage

from src.database.schema import DtrDocument, FirFirstDocument
from src.utils import storage as storage_module
from src.utils.storage import SessionWithStorage


FAKE_PDF = b'%PDF-1.4\n%%EOF\n'


def pdf_file(filename: str) -> FileStorage:
  return FileStorage(stream=BytesIO(FAKE_PDF), filename=filename, content_type='application/pdf')


def test_storage_and_database_are_committed_together(db, tmp_path):
  with SessionWithStorage() as session:
    stored_path = session.upload(pdf_file('committed.pdf'), 'committed.pdf', str(tmp_path), subfolder='documents')
    create(DtrDocument, {'link': stored_path}, session=session)
    session.commit()

  assert os.path.isfile(get_full_path(str(tmp_path), 'documents', filename='committed.pdf'))
  with Session() as session:
    assert session.query(DtrDocument).filter_by(link=stored_path).count() == 1


def test_session_without_commit_rolls_back_storage_and_database(db, tmp_path):
  stored_path = get_full_path(str(tmp_path), 'documents', filename='not-committed.pdf')

  with SessionWithStorage() as session:
    session.upload(pdf_file('not-committed.pdf'), 'not-committed.pdf', str(tmp_path), subfolder='documents')
    create(DtrDocument, {'link': stored_path}, session=session)

  assert not os.path.exists(stored_path)
  with Session() as session:
    assert session.query(DtrDocument).filter_by(link=stored_path).count() == 0


def test_database_failure_rolls_back_file_and_row(db, tmp_path):
  stored_path = get_full_path(str(tmp_path), 'documents', filename='rolled-back.pdf')

  with pytest.raises(IntegrityError):
    with SessionWithStorage() as session:
      session.upload(pdf_file('rolled-back.pdf'), 'rolled-back.pdf', str(tmp_path), subfolder='documents')
      create(FirFirstDocument, {'link': stored_path, 'disposal_id': 999_999_999}, session=session)
      session.commit()

  assert not os.path.exists(stored_path)
  with Session() as session:
    assert session.query(FirFirstDocument).filter_by(link=stored_path).count() == 0


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


def test_rollback_survives_missing_files(monkeypatch, tmp_path):
  """Un file già sparito dallo storage non deve interrompere la compensazione."""
  deleted = []

  def fake_delete(filename, folder, **kwargs):
    deleted.append(filename)
    if filename == 'ghost.pdf':
      raise FileNotFoundError(filename)
    if filename == 'broken.pdf':
      raise OSError('storage error')

  monkeypatch.setattr(storage_module, 'upload_file', lambda *a, **k: 'fake-path')
  monkeypatch.setattr(storage_module, 'delete_file', fake_delete)

  with SessionWithStorage() as storage:
    storage.upload(pdf_file('ghost.pdf'), 'ghost.pdf', str(tmp_path))
    storage.upload(pdf_file('broken.pdf'), 'broken.pdf', str(tmp_path))
    storage.upload(pdf_file('ok.pdf'), 'ok.pdf', str(tmp_path))

  # Compensazione in ordine inverso, senza fermarsi sugli errori
  assert deleted == ['ok.pdf', 'broken.pdf', 'ghost.pdf']


def test_getattr_raises_outside_context():
  storage = SessionWithStorage()
  with pytest.raises(AttributeError):
    storage.query

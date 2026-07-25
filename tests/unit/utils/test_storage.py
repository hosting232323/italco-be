import os
from io import BytesIO

import pytest
from api.storage import get_full_path
from api.storage import session as session_module
from api.storage.session import SessionWithStorage
from database_api import Session
from database_api.operations import create
from sqlalchemy.exc import IntegrityError
from werkzeug.datastructures import FileStorage

from src.database.schema import DtrDocument, FirFirstDocument


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


def test_nothing_is_published_before_commit(db, tmp_path):
  final_path = get_full_path(str(tmp_path), 'documents', filename='pending.pdf')

  with SessionWithStorage() as session:
    session.upload(pdf_file('pending.pdf'), 'pending.pdf', str(tmp_path), subfolder='documents')
    create(DtrDocument, {'link': final_path}, session=session)
    # Prima del commit il file non deve esistere nella destinazione finale.
    assert not os.path.exists(final_path)
    session.commit()

  assert os.path.isfile(final_path)


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


def test_multiple_uploaded_files_are_not_published_on_rollback(db, tmp_path):
  filenames = ['first.pdf', 'second.pdf']
  paths = [get_full_path(str(tmp_path), 'documents', filename=filename) for filename in filenames]

  with pytest.raises(RuntimeError, match='database failure'):
    with SessionWithStorage() as session:
      for filename in filenames:
        session.upload(pdf_file(filename), filename, str(tmp_path), subfolder='documents')
      raise RuntimeError('database failure')

  assert all(not os.path.exists(path) for path in paths)


def test_publish_failure_after_commit_does_not_break_the_request(db, tmp_path, monkeypatch):
  """Se la scrittura del file fallisce DOPO il commit, la riga resta salvata e
  l'errore non si propaga (verrà segnalato da check_mismatch, è recuperabile)."""
  stored_path = get_full_path(str(tmp_path), 'documents', filename='publish-fail.pdf')

  def failing_upload(*args, **kwargs):
    raise OSError('disk error')

  monkeypatch.setattr(session_module, 'upload_file', failing_upload)

  with SessionWithStorage() as session:
    session.upload(pdf_file('publish-fail.pdf'), 'publish-fail.pdf', str(tmp_path), subfolder='documents')
    create(DtrDocument, {'link': stored_path}, session=session)
    session.commit()  # non solleva

  assert not os.path.exists(stored_path)
  with Session() as session:
    assert session.query(DtrDocument).filter_by(link=stored_path).count() == 1


def test_deferred_delete_runs_only_after_commit(db, tmp_path, monkeypatch):
  deleted = []
  monkeypatch.setattr(session_module, 'delete_file', lambda filename, folder, **kwargs: deleted.append(filename))

  # Rollback: la delete non deve avvenire.
  with SessionWithStorage() as session:
    session.delete_file('keep.pdf', str(tmp_path), subfolder='documents')
  assert deleted == []

  # Commit: la delete viene eseguita.
  with SessionWithStorage() as session:
    session.delete_file('remove.pdf', str(tmp_path), subfolder='documents')
    session.commit()
  assert deleted == ['remove.pdf']


def test_getattr_raises_outside_context():
  storage = SessionWithStorage()
  with pytest.raises(AttributeError):
    storage.query

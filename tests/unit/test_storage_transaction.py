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
  DisposalFirstCopyDocument,
  Order,
  RaeDocument,
  RaeProduct,
  RaeProductGroup,
  User,
)
from src.end_points.rae import rae_bp
from src.utils.file import StorageTransaction
from tests.utils import auth_header_for


FAKE_PDF = b'%PDF-1.4\n%%EOF\n'


def pdf_file(filename: str) -> FileStorage:
  return FileStorage(stream=BytesIO(FAKE_PDF), filename=filename, content_type='application/pdf')


def test_storage_and_database_are_committed_together(seeded_db, tmp_path):
  with StorageTransaction() as storage:
    with Session() as session:
      stored_path = storage.upload(pdf_file('committed.pdf'), 'committed.pdf', str(tmp_path), subfolder='documents')
      create(DisposalFirstCopyDocument, {'link': stored_path}, session=session)
      session.commit()

  assert os.path.isfile(get_full_path(str(tmp_path), 'documents', False, 'committed.pdf'))
  with Session() as session:
    assert session.query(DisposalFirstCopyDocument).filter_by(link=stored_path).count() == 1


def test_database_failure_rolls_back_file_and_row(seeded_db, tmp_path):
  stored_path = get_full_path(str(tmp_path), 'documents', False, 'rolled-back.pdf')

  with pytest.raises(IntegrityError):
    with StorageTransaction() as storage:
      with Session() as session:
        storage.upload(pdf_file('rolled-back.pdf'), 'rolled-back.pdf', str(tmp_path), subfolder='documents')
        create(
          DisposalFirstCopyDocument,
          {'link': stored_path, 'disposal_id': 999_999_999},
          session=session,
        )
        session.commit()

  assert not os.path.exists(stored_path)
  with Session() as session:
    assert session.query(DisposalFirstCopyDocument).filter_by(link=stored_path).count() == 0


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
    document_count = session.query(RaeDocument).filter_by(rae_product_id=product_id).count()

  def fail_upload(*args, **kwargs):
    raise OSError('storage unavailable')

  monkeypatch.setattr(StorageTransaction, 'upload', fail_upload)

  app = Flask(__name__)
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
    assert session.query(RaeDocument).filter_by(rae_product_id=product_id).count() == document_count

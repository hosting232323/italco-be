import os

from flask import request
from sqlalchemy import text
from sqlalchemy.orm import Session as session_type

from database_api.operations import create

from ... import STATIC_FOLDER, get_base_file_path
from ...utils.file import StorageTransaction


def guess_next_id(session: session_type, model: str) -> int:
  return session.execute(text(f"SELECT nextval('{model}_id_seq')")).scalar()


def store_document(
  model,
  owner_field: str,
  owner_id: int,
  folder: str,
  session: session_type,
  storage: StorageTransaction,
):
  uploaded_file = next(iter(request.files.values()), None)
  if not uploaded_file or uploaded_file.mimetype != 'application/pdf':
    return None

  document_id = guess_next_id(session, model.__tablename__)
  filename = f'{document_id}.pdf'
  stored_path = storage.upload(uploaded_file, filename, STATIC_FOLDER, subfolder=folder.split('/')[-1])
  link = get_base_file_path(folder) + os.path.basename(stored_path)
  return create(model, {'id': document_id, owner_field: owner_id, 'link': link}, session=session)


def handle_document_by_name(
  data: dict,
  folder: str,
  model: str,
  field_name: str,
  session: session_type,
  storage: StorageTransaction,
) -> dict:
  uploaded_file = request.files.get(field_name)
  if not uploaded_file or uploaded_file.mimetype != 'application/pdf':
    return data

  filename = f'{guess_next_id(session, model)}.pdf'
  stored_path = storage.upload(uploaded_file, filename, STATIC_FOLDER, subfolder=folder.split('/')[-1])
  data[field_name] = get_base_file_path(folder) + os.path.basename(stored_path)
  return data

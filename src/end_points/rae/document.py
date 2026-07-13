import os

from sqlalchemy import text
from sqlalchemy.orm import Session as session_type

from database_api.operations import create

from ... import STATIC_FOLDER, get_base_file_path
from ...utils.storage import StorageTransaction


def guess_next_id(session: session_type, model: str) -> int:
  sequence_name = session.execute(
    text("SELECT pg_get_serial_sequence(:table_name, 'id')"),
    {'table_name': model},
  ).scalar_one()
  return session.execute(
    text('SELECT nextval(CAST(:sequence_name AS regclass))'),
    {'sequence_name': sequence_name},
  ).scalar_one()


def store_document(
  model,
  owner_field: str,
  owner_id: int,
  folder: str,
  uploaded_file,
  session: session_type,
  storage: StorageTransaction,
):
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
  uploaded_file,
  session: session_type,
  storage: StorageTransaction,
) -> dict:
  if not uploaded_file or uploaded_file.mimetype != 'application/pdf':
    return data

  filename = f'{guess_next_id(session, model)}.pdf'
  stored_path = storage.upload(uploaded_file, filename, STATIC_FOLDER, subfolder=folder.split('/')[-1])
  data[field_name] = get_base_file_path(folder) + os.path.basename(stored_path)
  return data

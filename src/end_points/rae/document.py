import os

from sqlalchemy.orm import Session as session_type

from api.storage.utils import guess_next_id, get_base_file_path
from database_api.operations import create

from ... import STATIC_FOLDER
from ...utils.storage import SessionWithStorage


def store_document(
  model,
  owner_field: str,
  owner_id: int,
  folder: str,
  uploaded_file,
  session: session_type,
  storage: SessionWithStorage,
):
  if not uploaded_file or uploaded_file.mimetype != 'application/pdf':
    return None

  document_id = guess_next_id(model.__tablename__, session=session)
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
  storage: SessionWithStorage,
) -> dict:
  if not uploaded_file or uploaded_file.mimetype != 'application/pdf':
    return data

  filename = f'{guess_next_id(model, session=session)}.pdf'
  stored_path = storage.upload(uploaded_file, filename, STATIC_FOLDER, subfolder=folder.split('/')[-1])
  data[field_name] = get_base_file_path(folder) + os.path.basename(stored_path)
  return data

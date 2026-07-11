import os

from flask import request
from sqlalchemy import text
from sqlalchemy.orm import Session as session_type

from api.storage import upload_file
from database_api.operations import create

from ... import STATIC_FOLDER, get_base_file_path


def guess_next_id(session: session_type, model: str) -> int:
  return session.execute(text(f"SELECT nextval('{model}_id_seq')")).scalar()


def store_document(model, owner_field: str, owner_id: int, folder: str, session: session_type):
  uploaded_file = next(iter(request.files.values()), None)
  if not uploaded_file or uploaded_file.mimetype != 'application/pdf':
    return None

  document_id = guess_next_id(session, model.__tablename__)
  link = get_base_file_path(folder) + os.path.basename(
    upload_file(uploaded_file, f'{document_id}.pdf', STATIC_FOLDER, 'local', folder.split('/')[-1])
  )
  return create(model, {'id': document_id, owner_field: owner_id, 'link': link}, session=session)


def handle_document_by_name(data: dict, folder: str, model: str, field_name: str, session: session_type) -> dict:
  uploaded_file = request.files.get(field_name)
  if not uploaded_file or uploaded_file.mimetype != 'application/pdf':
    return data

  data[field_name] = get_base_file_path(folder) + os.path.basename(
    upload_file(
      uploaded_file,
      f'{guess_next_id(session, model)}.pdf',
      STATIC_FOLDER,
      'local',
      folder.split('/')[-1],
    )
  )
  return data

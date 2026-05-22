import os
from sqlalchemy import text
from database_api import Session
from flask import request, send_from_directory
from sqlalchemy.orm import Session as session_type

from api.storage import upload_file
from ... import STATIC_FOLDER, IS_DEV, get_base_file_path


def handle_document(data: dict):
  with Session() as session:
    uploaded_file = next(iter(request.files.values()), None)
    if not uploaded_file:
      return data

    if uploaded_file.mimetype != 'application/pdf':
      return data

    data['link'] = get_base_file_path('rae/documents') + os.path.basename(
      upload_file(uploaded_file, f'{guess_next_id(session)}.pdf', STATIC_FOLDER, 'local', 'documents')
    )

    return data


def serve_document(filename: str):
  return send_from_directory(
    os.path.join(STATIC_FOLDER, 'test' if IS_DEV else 'prod', 'documents'),
    filename,
  )


def guess_next_id(session: session_type) -> int:
  return session.execute(text("SELECT nextval('rae_product_id_seq')")).scalar()

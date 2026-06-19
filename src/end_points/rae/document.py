import os
from database_api import Session
from flask import request

from api.storage import upload_file
from ...utils.file import guess_next_id
from ... import STATIC_FOLDER, get_base_file_path


def handle_document(data: dict, folder: str, model: str, field_name: str):
  with Session() as session:
    uploaded_file = next(iter(request.files.values()), None)
    if not uploaded_file:
      return data

    if uploaded_file.mimetype != 'application/pdf':
      return data

    data[field_name] = get_base_file_path(folder) + os.path.basename(
      upload_file(uploaded_file, f'{guess_next_id(session, model)}.pdf', STATIC_FOLDER, 'local', folder.split('/')[-1])
    )
    return data

import os
from flask import request

from ... import STATIC_FOLDER
from api.storage import upload_file
from api.storage.utils import guess_next_id, get_base_file_path


def handle_document(data: dict, folder: str, model: str, field_name: str) -> dict:
  uploaded_file = next(iter(request.files.values()), None)
  if not uploaded_file or uploaded_file.mimetype != 'application/pdf':
    return data

  data[field_name] = get_base_file_path(folder) + os.path.basename(
    upload_file(uploaded_file, f'{guess_next_id(model)}.pdf', STATIC_FOLDER, subfolder=folder.split('/')[-1])
  )
  return data


def handle_document_by_name(
  data: dict, folder: str, model: str, field_name: str, file_name: str
) -> dict:
  uploaded_file = request.files.get(file_name)
  if not uploaded_file or uploaded_file.mimetype != 'application/pdf':
    return data

  data[field_name] = get_base_file_path(folder) + os.path.basename(
    upload_file(uploaded_file, f'{guess_next_id(model)}.pdf', STATIC_FOLDER, 'local', folder.split('/')[-1])
  )
  return data

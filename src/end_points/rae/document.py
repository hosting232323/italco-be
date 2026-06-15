import os
from database_api import Session
from flask import request

from ... import STATIC_FOLDER
from api.storage import upload_file
from api.storage.utils import guess_next_id, get_base_file_path


def handle_document(data: dict):
  with Session() as session:
    uploaded_file = next(iter(request.files.values()), None)
    if not uploaded_file:
      return data

    if uploaded_file.mimetype != 'application/pdf':
      return data

    data['link'] = get_base_file_path('rae/dtr-documents') + os.path.basename(
      upload_file(
        uploaded_file, f'{guess_next_id(session, "rae_product")}.pdf', STATIC_FOLDER, subfolder='dtr-documents'
      )
    )

    return data

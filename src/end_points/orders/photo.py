import os
from flask import request
from sqlalchemy.orm import Session as session_type

from api.storage import upload_file
from database_api.operations import create
from ...database.schema import Photo, Order
from ... import STATIC_FOLDER, get_base_file_path
from ...utils.file import guess_next_id, guess_extension


def handle_photos(data: dict, order: Order, session: session_type):
  for file_key in request.files.keys():
    uploaded_file = request.files[file_key]
    if uploaded_file.mimetype in ['image/jpeg', 'image/png']:
      if file_key == 'signature':
        data['signature'] = uploaded_file.read()
      else:
        id = guess_next_id(session, 'photo')
        create(
          Photo,
          {
            'id': id,
            'order_id': order.id,
            'link': get_base_file_path('order/photos')
            + os.path.basename(
              upload_file(
                uploaded_file, f'{id}{guess_extension(uploaded_file.mimetype)}', STATIC_FOLDER, 'local', 'photos'
              )
            ),
          },
          session=session,
        )
  return data

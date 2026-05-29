import os
from sqlalchemy import text
from flask import request, send_from_directory
from sqlalchemy.orm import Session as session_type

from api.storage import upload_file
from database_api.operations import create
from ...database.schema import Photo, Order
from ... import STATIC_FOLDER, IS_DEV, get_base_file_path


def handle_photos(data: dict, order: Order, session: session_type):
  for file_key in request.files.keys():
    uploaded_file = request.files[file_key]
    if uploaded_file.mimetype in ['image/jpeg', 'image/png']:
      if file_key == 'signature':
        data['signature'] = uploaded_file.read()
      else:
        id = guess_next_id(session)
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


def serve_image(filename: str):
  return send_from_directory(
    os.path.join(STATIC_FOLDER, 'test' if IS_DEV else 'prod', 'photos'),
    filename,
  )


def guess_extension(mime_type: str) -> str:
  if mime_type == 'image/jpeg':
    return '.jpg'
  if mime_type == 'image/png':
    return '.png'
  if mime_type == 'image/webp':
    return '.webp'

  raise ValueError('Mime type non supportato')


def guess_next_id(session: session_type) -> int:
  return session.execute(text("SELECT nextval('photo_id_seq')")).scalar()

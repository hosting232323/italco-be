import os
from sqlalchemy import text
from flask import request, send_from_directory
from sqlalchemy.orm import Session as session_type

from api.storage import upload_file
from ... import STATIC_FOLDER, IS_DEV, API_PREFIX
from database_api.operations import create
from ...database.schema import Photo, Order


def handle_photos(data: dict, order: Order, session: session_type):
  for file_key in request.files.keys():
    uploaded_file = request.files[file_key]
    if uploaded_file.mimetype in ['image/jpeg', 'image/png']:
      if file_key == 'signature':
        data['signature'] = uploaded_file.read()
      else:
        id = guess_next_id(session)
        full_path = upload_file(
          uploaded_file,
          f'{id}{guess_extension(uploaded_file.mimetype)}',
          os.path.join(STATIC_FOLDER, 'photos'),
          'local',
        )
        protocol = f'http{"s" if not IS_DEV else ""}'
        api_prefix = f'/{API_PREFIX}' if API_PREFIX else ''
        create(
          Photo,
          {
            'id': id,
            'order_id': order.id,
            'link': f'{protocol}://{request.host}{api_prefix}/order/photos/{os.path.basename(full_path)}',
          },
          session=session,
        )
  return data


def serve_image(filename: str):
  return send_from_directory(
    os.path.join(STATIC_FOLDER, 'photos', 'test' if IS_DEV else 'prod'),
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

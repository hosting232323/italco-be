import os
from flask import request
from sqlalchemy import text
from sqlalchemy.orm import Session as session_type

from database_api.operations import create
from ...database.schema import Photo, Order


PHOTO_HOSTNAME = os.environ.get('PHOTO_HOSTNAME', None)
PHOTO_STORAGE_PATH = os.environ.get('PHOTO_STORAGE_PATH', 'static/photos/')


def handle_photos(data: dict, order: Order, session: session_type):
  for file_key in request.files.keys():
    uploaded_file = request.files[file_key]
    if uploaded_file.mimetype in ['image/jpeg', 'image/png']:
      if file_key == 'signature':
        data['signature'] = uploaded_file.read()
      else:
        filename = f'{guess_next_id(session)}{guess_extension(uploaded_file.mimetype)}'
        uploaded_file.save(os.path.join(PHOTO_STORAGE_PATH, filename))
        hostname = PHOTO_HOSTNAME if PHOTO_HOSTNAME else f'http://{request.host}/static/photos/'
        create(
          Photo,
          {'link': f'{hostname}{filename}', 'order_id': order.id},
          session=session,
        )
  return data


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

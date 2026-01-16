import os
from flask import request
from sqlalchemy import text
from sqlalchemy.orm import Session as session_type

from ... import STATIC_FOLDER
from api.storage import upload_file
from database_api.operations import create
from ...database.schema import Photo, Order


def handle_photos(data: dict, order: Order, session: session_type):
  for file_key in request.files.keys():
    uploaded_file = request.files[file_key]
    if uploaded_file.mimetype in ['image/jpeg', 'image/png']:
      if file_key == 'signature':
        data['signature'] = uploaded_file.read()
      else:
        create(
          Photo,
          {
            'order_id': order.id,
            'link': upload_file(
              uploaded_file,
              f'{guess_next_id(session)}{guess_extension(uploaded_file.mimetype)}',
              os.path.join(STATIC_FOLDER, 'photos'),
              'local',
            ),
          },
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

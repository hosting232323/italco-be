import os

from flask import request

from database_api.operations import create

from ... import STATIC_FOLDER
from ...database.schema import Order, Photo
from api.storage.utils import guess_extension, guess_next_id, get_base_file_path
from api.storage.session import SessionWithStorage


def handle_photos(data: dict, order: Order, session: SessionWithStorage):
  for file_key in request.files.keys():
    uploaded_file = request.files[file_key]
    if uploaded_file.mimetype in ['image/jpeg', 'image/png', 'image/webp']:
      if file_key == 'signature':
        data['signature'] = uploaded_file.read()
      else:
        photo_id = guess_next_id('photo', session=session)
        filename = f'{photo_id}{guess_extension(uploaded_file.mimetype)}'
        stored_path = session.upload(uploaded_file, filename, STATIC_FOLDER, subfolder='photos')
        create(
          Photo,
          {
            'id': photo_id,
            'order_id': order.id,
            'link': get_base_file_path('order/photos') + os.path.basename(stored_path),
          },
          session=session,
        )
  return data

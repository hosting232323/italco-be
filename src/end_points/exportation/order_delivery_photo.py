import base64
import os
from io import BytesIO
from urllib.parse import urlparse

from flask import render_template
from xhtml2pdf import pisa

from ... import STATIC_FOLDER, IS_DEV
from ...database.schema import Order, Photo, User
from database_api.operations import get_by_id
from ..orders.queries import format_query_result, query_orders
from .utils import export_pdf_attachment


def export_order_delivery_photo(user: User, photo_id: str):
  try:
    pid = int(photo_id)
  except ValueError:
    return {'status': 'ko', 'error': 'Id foto non valido'}
  photo = get_by_id(Photo, pid)
  if not photo:
    return {'status': 'ko', 'error': 'Foto non trovata'}
  order = get_by_id(Order, photo.order_id)
  if not order:
    return {'status': 'ko', 'error': 'Ordine non trovato'}
  orders = []
  for tupla in query_orders(user, [{'model': 'Order', 'field': 'id', 'value': order.id}]):
    orders = format_query_result(tupla, orders, user)
  if len(orders) != 1:
    return {'status': 'ko', 'error': 'Non autorizzato'}

  path_from_link = urlparse(photo.link).path
  filename = os.path.basename(path_from_link)
  if not filename:
    return {'status': 'ko', 'error': 'Link foto non valido'}
  subdir = 'test' if IS_DEV else 'prod'
  filepath = os.path.join(STATIC_FOLDER, 'photos', subdir, filename)
  if not os.path.isfile(filepath):
    return {'status': 'ko', 'error': 'File non trovato'}

  with open(filepath, 'rb') as f:
    img_bytes = f.read()

  ext = os.path.splitext(filename)[1].lower()
  if ext in ('.jpg', '.jpeg'):
    mime = 'image/jpeg'
  elif ext == '.png':
    mime = 'image/png'
  else:
    mime = 'image/jpeg'

  data_uri = f'data:{mime};base64,{base64.b64encode(img_bytes).decode("utf-8")}'

  result = BytesIO()
  pisa_status = pisa.CreatePDF(
    src=render_template('order_delivery_photo.html', image_data_uri=data_uri),
    dest=result,
  )
  if pisa_status.err:
    return {'status': 'ko', 'error': 'Errore nella creazione del PDF'}

  return export_pdf_attachment(result.getvalue(), filename=f'bolla_foto_{pid}.pdf')

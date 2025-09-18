from flask import request

from ... import IS_DEV
from api.email import send_email
from ...database.schema import Order
from ...database.enum import OrderStatus
from .queries import get_order_photo_ids


MAILS = (
  ['coppolagabriele973@gmail.com', 'massiitalco.mi@gmail.com']
  if not IS_DEV
  else ['coppolagabriele973@gmail.com', 'colasanto.giovanni.inf@gmail.com']
)


def mailer_check(order: Order, data: dict):
  if (
    ('status' in data and data['status'] in [OrderStatus.COMPLETED, OrderStatus.CANCELLED])
    or ('anomaly' in data and data['anomaly'] is True)
    or ('delay' in data and data['delay'] is True)
  ):
    photos_html = ''
    for photo_id in get_order_photo_ids(order.id):
      photo_url = f'{request.host_url}order/photo/{photo_id}'
      photos_html += f'<img src="{photo_url}" alt="Foto ordine" style="max-width:200px; margin:5px;"><br>'

    icons = []
    states = []
    if order.status == OrderStatus.COMPLETED:
      icons.append('✅')
      states.append('completato')
    elif order.status == OrderStatus.CANCELLED:
      icons.append('❌')
      states.append('non completato')
    if data.get('delay', False):
      icons.append('⏳')
      states.append('in ritardo')
    if data.get('anomaly', False):
      icons.append('⚠')
      states.append('con anomalia')

    subject = f'{" ".join(icons)} Ordine {order.id} {order.addressee} {" ".join(states)}'
    text = f'{" ".join(icons)} Ordine {order.id} {" ".join(states)}.\nMotivazione: {order.motivation}'
    html = f'{" ".join(icons)} Ordine {order.id} {" ".join(states)}.<br>Motivazione: {order.motivation}<br>Foto:<br>{photos_html}'
    for mail in MAILS:
      send_email(mail, {'text': text, 'html': html}, subject)

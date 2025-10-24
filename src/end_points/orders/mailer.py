from flask import request

from ... import IS_DEV
from api.email import send_email
from ...database.enum import OrderStatus
from ...database.schema import Order, Motivation
from .queries import get_order_photo_ids, get_user_by_order


MAILS = (
  ['coppolagabriele973@gmail.com']
  if not IS_DEV
  else ['coppolagabriele973@gmail.com', 'colasanto.giovanni.inf@gmail.com']
)


def get_mails(order: Order):
  if IS_DEV:
    return MAILS
  else:
    user = get_user_by_order(order)
    return list(set(MAILS + ([user.email] if user and user.email else [])))


def mailer_check(order: Order, data: dict, motivation: Motivation):
  if (
    ('status' in data and data['status'] in [OrderStatus.CANCELLED, OrderStatus.TO_RESCHEDULE])
    or ('anomaly' in data and data['anomaly'] is True)
    or ('delay' in data and data['delay'] is True)
  ):
    photos_html = ''
    for photo_id in get_order_photo_ids(order.id):
      photo_url = f'{request.host_url}order/photo/{photo_id}'
      photos_html += f'<img src="{photo_url}" alt="Foto ordine" style="max-width:200px; margin:5px;"><br>'

    icons = []
    states = []
    if order.status == OrderStatus.TO_RESCHEDULE:
      icons.append('🚧')
      states.append('da rischedulare')
    elif order.status == OrderStatus.CANCELLED:
      icons.append('❌')
      states.append('non completato')
    if data.get('delay', False):
      icons.append('⏳')
      states.append('in ritardo')
    if data.get('anomaly', False):
      icons.append('⚠')
      states.append('con anomalia')

    motivation_text = motivation.text if motivation else 'Nessuna motivazione fornita'
    subject = f'{" ".join(icons)} Ordine {order.id} {order.addressee} {" ".join(states)}'
    text = f'{" ".join(icons)} Ordine {order.id} {" ".join(states)}.\nMotivazione: {motivation_text}\nNote Punto Vendita: {order.customer_note}'
    html = f'{" ".join(icons)} Ordine {order.id} {" ".join(states)}.<br>Motivazione: {motivation_text}<br>Note Punto Vendita: {order.customer_note}<br>Foto:<br>{photos_html}'

    for mail in get_mails(order):
      send_email(mail, {'text': text, 'html': html}, subject)

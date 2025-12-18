from api.settings import IS_DEV
from api.email import send_email
from ...database.enum import OrderStatus
from ...database.schema import Order, Motivation
from .queries import get_order_photos, get_customer_user_by_order


MAILS = (
  ['coppolagabriele973@gmail.com']
  if not IS_DEV
  else ['coppolagabriele973@gmail.com', 'colasanto.giovanni.inf@gmail.com']
)


def get_mails(order: Order):
  if IS_DEV:
    return MAILS
  else:
    user = get_customer_user_by_order(order)
    return list(set(MAILS + ([user.email] if user and user.email else [])))


def mailer_check(order: Order, data: dict, motivation: Motivation):
  if (
    ('status' in data and data['status'] in [OrderStatus.CANCELLED, OrderStatus.TO_RESCHEDULE])
    or ('anomaly' in data and data['anomaly'] is True)
    or ('delay' in data and data['delay'] is True)
  ):
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
    html = (
      f'{" ".join(icons)} Ordine {order.id} {" ".join(states)}.<br>Motivazione: {motivation_text}<br>Note Punto Vendita: {order.customer_note}<br>Foto:<br>'
      + ''.join(
        [f'<img src="{photo.link}" alt="Photo" style="max-width:300px;"><br>' for photo in get_order_photos(order.id)]
      )
    )

    for mail in get_mails(order):
      send_email(mail, {'text': text, 'html': html}, subject)

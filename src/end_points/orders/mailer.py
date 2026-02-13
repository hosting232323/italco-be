from sqlalchemy import and_

from api.settings import IS_DEV
from api.email import send_email
from database_api import Session
from .queries import get_order_photos
from ...database.enum import OrderStatus
from ...database.schema import Order, Motivation, User, CustomerUserInfo, ServiceUser, Product


MAILS = (
  ['coppolagabriele973@gmail.com']
  if not IS_DEV
  else ['coppolagabriele973@gmail.com', 'colasanto.giovanni.inf@gmail.com']
)


def get_mails(order: Order):
  if IS_DEV:
    return MAILS
  else:
    user_info = get_user_mail(order)
    return list(set(MAILS + ([user_info.email] if user_info and user_info.email else [])))


def mailer_check(order: Order, data: dict, motivation: Motivation):
  if (
    ('status' in data and data['status'] in [OrderStatus.NOT_DELIVERED, OrderStatus.TO_RESCHEDULE])
    or ('anomaly' in data and data['anomaly'] is True)
    or ('delay' in data and data['delay'] is True)
  ):
    icons = []
    states = []
    if order.status == OrderStatus.TO_RESCHEDULE:
      icons.append('🚧')
      states.append('da rischedulare')
    elif order.status == OrderStatus.NOT_DELIVERED:
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


def get_user_mail(order: Order) -> CustomerUserInfo:
  with Session() as session:
    return (
      session.query(CustomerUserInfo)
      .join(User, User.id == CustomerUserInfo.user_id)
      .join(ServiceUser, ServiceUser.user_id == User.id)
      .join(Product, and_(Product.service_user_id == ServiceUser.id, Product.order_id == order.id))
      .first()
    )

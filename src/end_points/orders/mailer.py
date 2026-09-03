import os

from sqlalchemy import and_

from api.settings import IS_DEV
from api.email import send_email
from api.storage import get_full_path
from database_api import Session
from .queries import get_order_photos
from ... import STATIC_FOLDER
from ...database.enum import OrderStatus
from ...database.schema import Order, User, CustomerUserInfo, ServiceUser, Product


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


def mailer_check(order: Order, data: dict, motivation: str | None):
  if IS_DEV:
    return

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

    motivation_text = motivation or 'Nessuna motivazione fornita'
    subject = f'{" ".join(icons)} Ordine {order.id} {order.addressee} {" ".join(states)}'
    text = (
      f'{" ".join(icons)} Ordine {order.id} {" ".join(states)}.\n'
      f'Motivazione: {motivation_text}\nNote Punto Vendita: {order.customer_note}'
    )
    attachments = build_photo_attachments(order.id)
    photo_line = f'<br>Foto: {len(attachments)} in allegato' if attachments else '<br>Nessuna foto disponibile'
    html = (
      f'{" ".join(icons)} Ordine {order.id} {" ".join(states)}.<br>Motivazione: {motivation_text}'
      f'<br>Note Punto Vendita: {order.customer_note}{photo_line}'
    )

    for mail in get_mails(order):
      send_email(
        mail,
        {'text': text, 'html': html},
        subject,
        attachments=attachments,
        signature={
          'text': (
            '--\n'
            'Ares Logistics - Italco.mi Logistribuzioni srls\n'
            'Sede legale: Via Emanuele Filiberto Duca 24/A, 72023 Mesagne (BR)\n'
            'P. IVA IT02735550747\n'
            'PEC: italco.misrls@pec.it\n'
            'www.ares-logistics.it'
          ),
          'html': (
            '<hr style="border:none;border-top:1px solid #ddd;margin:12px 0">'
            '<div style="font-size:12px;color:#666;line-height:1.5">'
            '<strong>Ares Logistics</strong> - Italco.mi Logistribuzioni srls<br>'
            'Sede legale: Via Emanuele Filiberto Duca 24/A, 72023 Mesagne (BR)<br>'
            'P. IVA IT02735550747<br>'
            'PEC: <a href="mailto:italco.misrls@pec.it">italco.misrls@pec.it</a><br>'
            '<a href="https://www.ares-logistics.it">www.ares-logistics.it</a>'
            '</div>'
          ),
        },
      )


def build_photo_attachments(order_id: int) -> list[dict]:
  attachments = []
  folder = get_full_path(STATIC_FOLDER, 'photos')
  for photo in get_order_photos(order_id):
    filename = os.path.basename(photo.link)
    with open(os.path.join(folder, filename), 'rb') as file:
      attachments.append({'content': file.read(), 'filename': filename})
  return attachments


def get_user_mail(order: Order) -> CustomerUserInfo:
  with Session() as session:
    return (
      session.query(CustomerUserInfo)
      .join(User, User.id == CustomerUserInfo.user_id)
      .join(ServiceUser, ServiceUser.user_id == User.id)
      .join(Product, and_(Product.service_user_id == ServiceUser.id, Product.order_id == order.id))
      .first()
    )

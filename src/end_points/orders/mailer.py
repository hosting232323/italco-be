from flask import request
from api.email import send_email
from ...database.schema import Order
from ...database.enum import OrderStatus
from .queries import get_order_photo_ids

DEFAULT_MAILS = [
  'cldevofficial@gmail.com'
]


def mailer_check(order: Order, data: dict):
  subject = ''
  text_body = ''
  html_body = ''
  photos_html = ''
  
  photo_ids = get_order_photo_ids(order.id)
  
  for photo_id in photo_ids:
    photo_url = f"{request.host_url}/order/photo/{photo_id}"
    photos_html += f'<img src="{photo_url}" alt="Foto ordine" style="max-width:200px; margin:5px;"><br>'
  
  if order.status == OrderStatus.COMPLETED:
    subject = f"✅ Ordine {order.id} {order.addressee} completato"
    text_body = f"Il tuo ordine {order.id} {order.addressee} è stato completato con successo.\nIndirizzo consegna: {order.address}.\nGrazie per aver scelto il nostro servizio!"
    html_body = f"<p>Il tuo ordine <b>{order.id}</b> {order.addressee} è stato completato con successo.</p><p>Indirizzo consegna: {order.address}</p>{photos_html}<p>Grazie per aver scelto il nostro servizio!</p>"
  
  elif data.get('delay', False):
    subject = f"⏳ Ordine {order.id} in ritardo"
    motivo = data.get('reason', 'Motivo non specificato')
    text_body = f"Il tuo ordine {order.id} {order.addressee} subirà un ritardo.\nIndirizzo consegna: {order.address}\nMotivazione: {motivo}\nGrazie per aver scelto il nostro servizio!"
    html_body = f"<p>Il tuo ordine <b>{order.id}</b> {order.addressee} subirà un ritardo.</p><p>Indirizzo consegna: {order.address}</p><p>Motivazione: {motivo}</p>{photos_html}<p>Grazie per aver scelto il nostro servizio!</p>"
  
  elif data.get('anomaly', False):
    subject = f"⚠ Anomalia ordine {order.id}"
    motivo = data.get('reason', 'Anomalia non specificata')
    text_body = f"Il tuo ordine {order.id} {order.addressee} - Indirizzo consegna: {order.address}\nNella gestione dell’ordine è stata riscontrata una anomalia: {motivo}\nGrazie per aver scelto il nostro servizio!"
    html_body = f"<p>Il tuo ordine <b>{order.id}</b> {order.addressee} - Indirizzo consegna: {order.address}</p><p>Nella gestione dell’ordine è stata riscontrata una anomalia: {motivo}</p>{photos_html}<p>Grazie per aver scelto il nostro servizio!</p>"
  
  elif order.status == OrderStatus.CANCELLED:
    subject = f"❌ Ordine {order.id} non consegnato"
    motivo = data.get('reason', 'Motivo non specificato')
    text_body = f"Il tuo ordine {order.id} {order.addressee} - Indirizzo consegna: {order.address}.\nNon è stato consegnato: {motivo}\nGrazie per aver scelto il nostro servizio!"
    html_body = f"<p>Il tuo ordine <b>{order.id}</b> {order.addressee} - Indirizzo consegna: {order.address}</p><p>Non è stato consegnato: {motivo}</p>{photos_html}<p>Grazie per aver scelto il nostro servizio!</p>"

  body = {
    'text': text_body,
    'html': html_body
  }
  
  send_email('cldevofficial@gmail.com', body, subject)
  
  # if ('status' in data and data['status'] in [OrderStatus.CANCELLED, OrderStatus.ON_BOARD]) or \
  #    ('anomaly' in data and data['anomaly'] is True) or \
  #    ('delay' in data and data['delay'] is True):
  #   for mail in DEFAULT_MAILS:
  #     send_email(
  #       mail,
  #       f'Ordine: {order.id} aggiornato',
  #       f'Ordine di tipo: {order.status}'
  #     )

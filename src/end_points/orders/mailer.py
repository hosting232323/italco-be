from api.email import send_email
from ...database.schema import Order
from ...database.enum import OrderStatus


DEFAULT_MAILS = [
  'colasanto.giovanni.inf@gmail.com',
  'coppolagabriele973@gmail.com'
]


def mailer_check(order: Order, data: dict):
  if ('status' in data and data['status'] in [OrderStatus.CANCELLED, OrderStatus.ON_BOARD]) or \
     ('anomaly' in data and data['anomaly'] is True) or \
     ('delay' in data and data['delay'] is True):
    for mail in DEFAULT_MAILS:
      send_email(
        mail,
        f'Ordine: {order.id} aggiornato',
        f'Ordine di tipo: {order.status}'
      )

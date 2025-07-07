from api.email import send_email
from ...database.schema import Order
from ...database.enum import OrderStatus


DEFAULT_MAILS = [
  'colasanto.giovanni.inf@gmail.com'
]


def mailer_check(order: Order):
  if order.status in [OrderStatus.ANOMALY, OrderStatus.CANCELLED, OrderStatus.ON_BOARD]:
    for mail in DEFAULT_MAILS:
      send_email(
        mail,
        f'Ordine: {order.id} aggiornato',
        f'Ordine di tipo: {order.status}'
      )

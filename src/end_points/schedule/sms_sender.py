import os

from ... import IS_DEV
from api.sms import send_sms
from ...database.schema import Order
from ..orders.queries import get_selling_point
from ..orders.sms_sender import get_order_link


def schedule_sms_check(order: Order, was_unscheduled: bool = True):
  if not IS_DEV and was_unscheduled and order.addressee_contact:
    start = order.start_time_slot.strftime('%H:%M')
    end = order.end_time_slot.strftime('%H:%M')
    send_sms(
      os.environ['VONAGE_API_KEY'],
      os.environ['VONAGE_API_SECRET'],
      'Ares',
      order.addressee_contact,
      f'ARES ITALCO.MI - Gentile Cliente, la consegna relativa al Punto Vendita: {get_selling_point(order).nickname}, è programmata per il '
      f"{order.assignament_date}, fascia {start} - {end}. Riceverà un preavviso di 30 minuti prima dell'arrivo. Per monitorare ogni "
      f'fase della sua consegna clicchi il link in questione {get_order_link(order)}. La preghiamo di garantire la presenza e la reperibilità '
      'al numero indicato. Buona Giornata!',
    )

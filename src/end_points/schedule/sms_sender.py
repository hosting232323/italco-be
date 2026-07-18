import os

from api.sms import send_sms
from api.settings import IS_DEV
from ..orders.queries import get_selling_point
from ..orders.sms_sender import get_order_link, format_time_slot
from ...database.schema import Order, ScheduleItem


def schedule_sms_check(order: Order, schedule_item: ScheduleItem):
  if not IS_DEV and order.addressee_contact:
    send_sms(
      os.environ['VONAGE_API_KEY'],
      os.environ['VONAGE_API_SECRET'],
      'Ares',
      order.addressee_contact,
      f'ARES ITALCO.MI - Gentile Cliente, la consegna relativa al Punto Vendita: {get_selling_point(order).nickname}'
      f', è programmata per il {order.booking_date}, fascia {format_time_slot(schedule_item.start_time_slot)} - '
      f"{format_time_slot(schedule_item.end_time_slot)}. Riceverà un preavviso di 30 minuti prima dell'arrivo. Per "
      f'monitorare ogni fase della sua consegna clicchi il link in questione {get_order_link(order)}. La preghiamo di'
      ' garantire la presenza e la reperibilità al numero indicato. Buona Giornata!',
    )

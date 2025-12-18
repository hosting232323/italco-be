import os

from api.sms import send_sms
from api.settings import IS_DEV
from ..orders.queries import get_selling_point
from ..orders.sms_sender import get_order_link
from ...database.schema import Order, ScheduleItem


def schedule_sms_check(order: Order, schedule_item: ScheduleItem):
  if not IS_DEV and order.addressee_contact:
    send_sms(
      os.environ['VONAGE_API_KEY'],
      os.environ['VONAGE_API_SECRET'],
      'Ares',
      order.addressee_contact,
      f'ARES ITALCO.MI - Gentile Cliente, la consegna relativa al Punto Vendita: {get_selling_point(order).nickname}, è programmata per il '
      f'{order.assignament_date}, fascia {schedule_item.start_time_slot.strftime("%H:%M")} - {schedule_item.end_time_slot.strftime("%H:%M")}'
      f". Riceverà un preavviso di 30 minuti prima dell'arrivo. Per monitorare ogni fase della sua consegna clicchi il link in questione "
      f'{get_order_link(order)}. La preghiamo di garantire la presenza e la reperibilità al numero indicato. Buona Giornata!',
    )

import os
from flask import request
from hashids import Hashids
from api.sms import send_sms

from api.settings import IS_DEV
from .queries import get_selling_point
from ...database.schema import Order, ScheduleItem


hashids = Hashids(salt='mia-chiave-segreta-super-segreta', min_length=8)


def format_time_slot(value) -> str:
  # Le fasce orarie possono essere time (dal DB) o stringhe 'HH:MM' (dal payload
  # appena assegnato all'entità e non ancora ricaricato).
  return value.strftime('%H:%M') if hasattr(value, 'strftime') else str(value)[:5]


def delay_sms_check(order: Order, schedule_item: ScheduleItem):
  if not IS_DEV and order.addressee_contact:
    send_sms(
      os.environ['VONAGE_API_KEY'],
      os.environ['VONAGE_API_SECRET'],
      'Ares',
      order.addressee_contact,
      f'ARES ITALCO.MI - Gentile Cliente, la consegna relativa al Punto Vendita: {get_selling_point(order).nickname}, '
      f'è stata riprogrammata per il {order.booking_date}, fascia {format_time_slot(schedule_item.start_time_slot)}'
      f" - {format_time_slot(schedule_item.end_time_slot)}. Riceverà un preavviso di 30 minuti prima dell'arrivo. "
      f'Per monitorare ogni fase della sua consegna clicchi il link in questione {get_order_link(order)}. La preghiamo'
      'di garantire la presenza e la reperibilità al numero indicato. Buona Giornata!',
    )


def get_order_link(order: Order) -> str:
  return f'{request.headers.get("Origin")}/order/{hashids.encode(order.id)}'

import os
from flask import request
from hashids import Hashids
from api.sms import send_sms
from datetime import datetime

from ... import IS_DEV
from ...database.schema import Order
from .queries import get_selling_point


hashids = Hashids(salt='mia-chiave-segreta-super-segreta', min_length=8)


def delay_sms_check(order: Order, data: dict, previous_start: datetime.time, previous_end: datetime.time):
  if (
    not IS_DEV
    and 'delay' in data
    and data['delay']
    and order.addressee_contact
    and (parse_time(data['start_time_slot']) != previous_start or parse_time(data['end_time_slot']) != previous_end)
  ):
    start = order.start_time_slot.strftime('%H:%M')
    end = order.end_time_slot.strftime('%H:%M')
    send_sms(
      os.environ['VONAGE_API_KEY'],
      os.environ['VONAGE_API_SECRET'],
      'Ares',
      order.addressee_contact,
      f'ARES ITALCO.MI - Gentile Cliente, la consegna relativa al Punto Vendita: {get_selling_point(order).nickname}, è stata riprogrammata per il '
      f"{order.assignament_date}, fascia {start} - {end}. Riceverà un preavviso di 30 minuti prima dell'arrivo. Per monitorare ogni fase della "
      f'sua consegna clicchi il link in questione {get_order_link(order)}. La preghiamo di garantire la presenza e la reperibilità al numero indicato. '
      'Buona Giornata!',
    )


def parse_time(value: str) -> datetime.time:
  for fmt in ['%H:%M', '%H:%M:%S']:
    try:
      return datetime.strptime(value, fmt).time()
    except ValueError:
      continue
  raise ValueError(f'Formato orario non riconosciuto: {value}')


def get_order_link(order: Order) -> str:
  return f'{request.headers.get("Origin")}/order/{hashids.encode(order.id)}'

import os
from flask import request
from hashids import Hashids
from api.sms import send_sms

from ... import IS_DEV
from ...database.schema import Order
from .queries import get_selling_point


hashids = Hashids(salt='mia-chiave-segreta-super-segreta', min_length=8)


def delay_sms_check(order: Order, data: dict):
  if (
    #  not IS_DEV
    'delay' in data
    and data['delay']
    and order.addressee_contact
  ):
    start = order.start_time_slot.strftime('%H:%M')
    end = order.end_time_slot.strftime('%H:%M')
    print(
      f'ARES ITALCO.MI - Gentile Cliente, la consegna relativa al Punto Vendita: {get_selling_point(order).nickname}, è stata riprogrammata per il '
      f"{order.assignament_date}, fascia {start} - {end}. Riceverà un preavviso di 30 minuti prima dell'arrivo. Per monitorare ogni fase della "
      f'sua consegna clicchi il link in questione {get_order_link(order)}. La preghiamo di garantire la presenza e la reperibilità al numero indicato. '
      'Buona Giornata!',
    )


def get_order_link(order: Order) -> str:
  return f'{request.headers.get("Origin")}/order/{hashids.encode(order.id)}'

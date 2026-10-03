import os
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from flask import request
from api.sms import send_sms
from database_api import Session

from api.settings import IS_DEV
from ... import allowed_origins
from .queries import get_selling_point
from ...database.schema import Order, OrderTrackingToken, ScheduleItem


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


def create_order_tracking_token(order: Order) -> str:
  token = secrets.token_urlsafe(32)
  token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
  with Session() as session:
    session.add(
      OrderTrackingToken(
        company_id=order.company_id,
        order_id=order.id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=90),
      )
    )
    session.commit()

  return token


def get_order_link(order: Order) -> str:
  token = create_order_tracking_token(order)
  request_origin = request.headers.get('Origin')
  base_url = request_origin if request_origin in allowed_origins else allowed_origins[0]
  return f'{base_url}/order/track#{token}'

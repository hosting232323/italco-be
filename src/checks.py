import os
import re
from sqlalchemy import or_, cast, String

from database_api import Session
from api.storage import check_mismatch
from api.telegram import send_telegram_message
from sqlalchemy.orm import Session as session_type
from .database.schema import Order, Product, ServiceUser, Schedule, Photo, History


missing_photos_path = os.path.join(
  os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src', 'assets', 'missing_photos.txt'
)
with open(missing_photos_path, 'r', encoding='utf-8') as file:
  MISSING_PHOTOS = [int(id) for id in re.findall(r'id:\s*(\d+)', file.read())]


def trigger_checks(folder):
  database_integrity_test()
  check_mismatch(get_all_files(), os.path.join(folder, 'photos'), 'Photos', 'local')

  return {'status': 'ok', 'message': 'Check eseguiti con successo'}


def database_integrity_test():
  with Session() as session:
    checks = get_checks()
    message_lines = ['*📊 Report Dati Corrotti*']

    for check in checks:
      message_lines.append(f'\n*{check["name"]}:*')

      results = check['query_fn'](session)

      if results:
        for item in results:
          message_lines.append(check['formatter'](item))
      else:
        message_lines.append(check['empty_msg'])

  send_telegram_message('\n'.join(message_lines))


def get_all_files() -> set[str]:
  with Session() as session:
    return [
      row.link.replace('https://ares-logistics.it/api/photos/prod/', '')
      for row in session.query(Photo).filter(Photo.id.not_in(MISSING_PHOTOS)).all()
    ]


def get_checks():
  return [
    {
      'name': '⚠️ Schedules con problemi',
      'query_fn': check_schedules,
      'formatter': format_schedule_issue,
      'empty_msg': '✔️ Nessun problema trovato.',
    },
    {
      'name': '❌ Ordini senza utente',
      'query_fn': check_orders_no_user,
      'formatter': format_order,
      'empty_msg': '✔️ Nessun ordine senza utente.',
    },
    {
      'name': '❌ Ordini senza prodotti',
      'query_fn': check_orders_no_product,
      'formatter': format_order,
      'empty_msg': '✔️ Nessun ordine senza prodotti.',
    },
    {
      'name': '❌ Storico non valido',
      'query_fn': check_history_invalid_status,
      'formatter': format_history_invalid,
      'empty_msg': '✔️ Nessun ordine con storico non valido.',
    },
  ]


def check_schedules(session: session_type):
  results = []
  for sched in session.query(Schedule).all():
    missing = []
    if not sched.schedule_item:
      missing.append('ScheduleItem')
    if not sched.delivery_group:
      missing.append('DeliveryGroup')

    if missing:
      results.append(
        {
          'schedule_id': sched.id,
          'date': sched.date.isoformat(),
          'transport_id': sched.transport_id,
          'missing': missing,
        }
      )
  return results


def check_orders_no_user(session: session_type):
  orders = session.query(Order).outerjoin(Product).outerjoin(ServiceUser).filter(ServiceUser.id.is_(None)).all()
  return [{'order_id': o.id, 'addressee': o.addressee, 'status': o.status.value} for o in orders]


def check_orders_no_product(session: session_type):
  orders = session.query(Order).outerjoin(Product).filter(Product.id.is_(None)).all()
  return [{'order_id': o.id, 'addressee': o.addressee, 'status': o.status.value} for o in orders]


def check_history_invalid_status(session: session_type):
  return (
    session.query(History)
    .filter(
      or_(
        History.status.is_(None),
        cast(History.status['value'], String) == 'null',
        cast(History.status['type'], String) == 'null',
      )
    )
    .all()
  )


def format_schedule_issue(s):
  missing_str = ', '.join(s['missing'])
  return (
    f'- Schedule ID {s["schedule_id"]} | Data: {s["date"]} | Trasporto: {s["transport_id"]} | Mancano: {missing_str}'
  )


def format_order(o):
  return f'- Order ID {o["order_id"]} | Destinatario: {o["addressee"]} | Stato: {o["status"]}'


def format_history_invalid(h):
  return f'- History ID {h.id} | Order ID: {h.order_id} | Status: {h.status}'

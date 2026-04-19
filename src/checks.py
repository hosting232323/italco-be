import os
import re

from database_api import Session
from api.storage import check_mismatch
from api.telegram import send_telegram_message
from .database.schema import Order, Product, ServiceUser, Schedule, Photo


missing_photos_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'missing_photos.txt')
with open(missing_photos_path, 'r', encoding='utf-8') as file:
  MISSING_PHOTOS = [int(id) for id in re.findall(r'id:\s*(\d+)', file.read())]


def trigger_checks(folder):
  database_integrity_test()
  check_mismatch(get_all_files(), os.path.join(folder, 'photos'), 'Photos', 'local')

  return {'status': 'ok', 'message': 'Check eseguiti con successo'}


def get_all_files() -> set[str]:
  with Session() as session:
    return [
      row.link.replace('https://ares-logistics.it/api/photos/prod/', '')
      for row in session.query(Photo).filter(Photo.id.not_in(MISSING_PHOTOS)).all()
    ]


def database_integrity_test():
  with Session() as session:
    # --- Schedule senza ScheduleItem o DeliveryGroup ---
    schedules = session.query(Schedule).all()
    schedule_issues = []
    for sched in schedules:
      missing = []
      if not sched.schedule_item:
        missing.append('ScheduleItem')
      if not sched.delivery_group:
        missing.append('DeliveryGroup')
      if missing:
        schedule_issues.append(
          {
            'schedule_id': sched.id,
            'date': sched.date.isoformat(),
            'missing': missing,
            'transport_id': sched.transport_id,
          }
        )

    # --- Ordini senza utenti associati ---
    orders_no_user = (
      session.query(Order).outerjoin(Product).outerjoin(ServiceUser).filter(ServiceUser.id.is_(None)).all()
    )
    orders_no_user_result = [
      {'order_id': o.id, 'addressee': o.addressee, 'status': o.status.value} for o in orders_no_user
    ]

    # --- Ordini senza prodotti ---
    orders_no_product = session.query(Order).outerjoin(Product).filter(Product.id.is_(None)).all()
    orders_no_product_result = [
      {'order_id': o.id, 'addressee': o.addressee, 'status': o.status.value} for o in orders_no_product
    ]

  message_lines = ['*📊 Report Dati Corrotti*\n\n*⚠️ Schedules con problemi:*']
  if schedule_issues:
    for s in schedule_issues:
      missing_str = ', '.join(s['missing'])
      message_lines.append(
        f'- Schedule ID {s["schedule_id"]} | Data: {s["date"]} | '
        f'Trasporto: {s["transport_id"]} | Mancano: {missing_str}'
      )
  else:
    message_lines.append('✔️ Nessun problema trovato.')

  message_lines.append('\n*❌ Ordini senza utente:*')
  if orders_no_user_result:
    for o in orders_no_user_result:
      message_lines.append(f'- Order ID {o["order_id"]} | Destinatario: {o["addressee"]} | Stato: {o["status"]}')
  else:
    message_lines.append('✔️ Nessun ordine senza utente.')

  message_lines.append('\n*❌ Ordini senza prodotti:*')
  if orders_no_product_result:
    for o in orders_no_product_result:
      message_lines.append(f'- Order ID {o["order_id"]} | Destinatario: {o["addressee"]} | Stato: {o["status"]}')
  else:
    message_lines.append('✔️ Nessun ordine senza prodotti.')

  send_telegram_message('\n'.join(message_lines))

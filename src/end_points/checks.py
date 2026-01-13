from flask import Blueprint

from database_api import Session
from api.telegram import send_telegram_message
from api import error_catching_decorator, swagger_decorator
from ..database.schema import Order, Product, ServiceUser, Schedule


checks_bp = Blueprint('checks_bp', __name__)


@checks_bp.route('', methods=['GET'])
@error_catching_decorator
@swagger_decorator
def check_mismatch():
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

  message_lines = ['*📊 Report Check Mismatch*\n']
  message_lines.append('*⚠️ Schedules con problemi:*')
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

  message = '\n'.join(message_lines)
  send_telegram_message(message)

  return {'status': 'ok', 'message': 'Check eseguiti con successo'}

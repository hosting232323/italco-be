from flask import Blueprint

from database_api import Session
from api import error_catching_decorator
from api.telegram import send_telegram_message
from ..database.schema import Order, Product, ServiceUser, Schedule


checks_bp = Blueprint('checks_bp', __name__)


@checks_bp.route('', methods=['GET'])
@error_catching_decorator
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

  send_telegram_message(
    '*📊 Report Check Mismatch*\n\n'
    f'*Schedules con problemi:* {schedule_issues}\n'
    f'*Ordini senza utente:* {orders_no_user_result}\n'
    f'*Ordini senza prodotti:* {orders_no_product_result}\n\n'
  )
  return {'status': 'ok', 'message': 'Check eseguiti con successo'}

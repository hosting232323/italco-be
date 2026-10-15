from flask import request
from .database.schema import User
from .database.enum import UserRole
from .database.seed import seed_data
from database_api import set_database
from api.settings import IS_DEV
from . import app, DATABASE_URL, LOCAL_PORT
from .end_points import flask_session_authentication

from .end_points.log import log_bp
from .end_points.rae import rae_bp
from .end_points.users import user_bp
from .end_points.orders import order_bp
from .end_points.chatty import chatty_bp
from .end_points.demo_request import demo_request_bp
from .end_points.company import company_bp
from .end_points.service import service_bp
from .end_points.schedule import schedule_bp
from .end_points.importation import import_bp
from .end_points.exportation import export_bp
from .end_points.transport import transport_bp
from .end_points.dashboard import dashboard_bp
from .end_points.customer_group import customer_group_bp
from .end_points.collection_point import collection_point_bp
from .end_points.service.constraint import check_services_date
from .end_points.customer_rule import customer_rules_bp, check_customer_rules
from .end_points.geographic_zone import geographic_zone_bp
from .end_points.delivery_coverage import (
  check_delivery_coverage_slots,
  delivery_coverage_bp,
  query_entries_for_cap,
)


def _group_blocked_days(blocked: dict) -> list[dict]:
  """{giorno: motivo} -> [{'reason', 'dates'}] con i giorni raggruppati per motivo."""
  grouped = {}
  for day in sorted(blocked):
    grouped.setdefault(blocked[day], []).append(day)
  return [{'reason': reason, 'dates': days} for reason, days in grouped.items()]


@app.route('/check-constraints', methods=['POST'])
@flask_session_authentication([UserRole.CUSTOMER])
def check_constraints(user: User):
  # Il vincolo geografico (Constraint su GeographicZone) è sostituito dalla
  # copertura corrieri: le date disponibili sono quelle coperte da un blocco
  # per il CAP del cliente con capienza per i servizi, incrociate coi vincoli
  # per cliente e per servizio.
  # Le fasce si calcolano una volta sola: le date coperte sono le loro chiavi,
  # e il calendario le mostra per farle scegliere al cliente al posto della dpc.
  # Motivi dei giorni bloccati e riempimento delle fasce sono diagnostica per
  # gli ambienti di test/demo: in produzione non si calcolano ne' si inviano.
  blocked = {} if IS_DEV else None
  slot_notes = {} if IS_DEV else None
  slots = check_delivery_coverage_slots(user=user, blocked_out=blocked, slot_notes_out=slot_notes)
  rule_dates = set(check_customer_rules(user))
  service_dates = set(check_services_date())
  dates = sorted(rule_dates & set(slots) & service_dates)
  # Giorni coperti ma non selezionabili, col motivo: il calendario li elenca
  # perche' il cliente capisca cosa manca invece di vedere date sparite. Le
  # regole del cliente e dei servizi hanno la precedenza sulla copertura.
  for day in set(blocked or {}) | (set(slots) if IS_DEV else set()):
    if day in rule_dates and day in service_dates:
      continue
    blocked[day] = (
      'Limite ordini giornalieri del punto vendita raggiunto o giorno escluso'
      if day not in rule_dates
      else 'Limite ordini giornalieri dei servizi scelti raggiunto'
    )
  # `covered` distingue l'indirizzo fuori da ogni blocco di copertura (il cliente
  # sceglie la data a mano) dalle fasce esaurite (nessuna data da scegliere).
  payload = request.json or {}
  cap = str(payload['cap']) if payload.get('cap') is not None else None
  covered = bool(cap and query_entries_for_cap(cap, address=payload.get('address')))
  visible_slots = {day: slots[day] for day in dates if day in slots}
  response = {'status': 'ok', 'dates': dates, 'slots': visible_slots, 'covered': covered}
  if IS_DEV:
    response['blocked'] = _group_blocked_days(blocked)
    # Fasce bloccate dei giorni selezionabili, col motivo.
    response['slot_notes'] = {day: notes for day, notes in slot_notes.items() if day in visible_slots}
  return response


app.register_blueprint(log_bp, url_prefix='/log')
app.register_blueprint(rae_bp, url_prefix='/rae')
app.register_blueprint(user_bp, url_prefix='/user')
app.register_blueprint(order_bp, url_prefix='/order')
app.register_blueprint(chatty_bp, url_prefix='/chatty')
app.register_blueprint(demo_request_bp, url_prefix='/demo-request')
app.register_blueprint(import_bp, url_prefix='/import')
app.register_blueprint(export_bp, url_prefix='/export')
app.register_blueprint(company_bp, url_prefix='/company')
app.register_blueprint(service_bp, url_prefix='/service')
app.register_blueprint(schedule_bp, url_prefix='/schedule')
app.register_blueprint(transport_bp, url_prefix='/transport')
app.register_blueprint(dashboard_bp, url_prefix='/dashboard')
app.register_blueprint(delivery_coverage_bp, url_prefix='/delivery-coverage')
app.register_blueprint(customer_rules_bp, url_prefix='/customer-rule')
app.register_blueprint(customer_group_bp, url_prefix='/customer-group')
app.register_blueprint(geographic_zone_bp, url_prefix='/geographic-zone')
app.register_blueprint(collection_point_bp, url_prefix='/collection-point')


set_database(DATABASE_URL)


if __name__ == '__main__':
  seed_data()
  app.run(host='0.0.0.0', port=LOCAL_PORT, debug=True)

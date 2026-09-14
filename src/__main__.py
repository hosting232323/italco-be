from .database.schema import User
from .database.enum import UserRole
from .database.seed import seed_data
from database_api import set_database
from . import app, DATABASE_URL, LOCAL_PORT
from .end_points import flask_session_authentication

from .end_points.log import log_bp
from .end_points.rae import rae_bp
from .end_points.users import user_bp
from .end_points.orders import order_bp
from .end_points.chatty import chatty_bp
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
from .end_points.delivery_coverage import delivery_coverage_bp, check_delivery_coverage, check_delivery_coverage_slots


@app.route('/check-constraints', methods=['POST'])
@flask_session_authentication([UserRole.CUSTOMER])
def check_constraints(user: User):
  # Il vincolo geografico (Constraint su GeographicZone) è sostituito dalla
  # copertura corrieri: le date disponibili sono quelle coperte da un blocco
  # per il CAP del cliente con capienza per i servizi, incrociate coi vincoli
  # per cliente e per servizio.
  dates = sorted(list(set(check_customer_rules(user)) & set(check_delivery_coverage()) & set(check_services_date())))
  # Le fasce orarie viaggiano solo per le date effettivamente ammesse: il
  # calendario le mostra per farle scegliere al cliente al posto della dpc.
  slots = check_delivery_coverage_slots()
  return {
    'status': 'ok',
    'dates': dates,
    'slots': {day: slots[day] for day in dates if day in slots},
  }


app.register_blueprint(log_bp, url_prefix='/log')
app.register_blueprint(rae_bp, url_prefix='/rae')
app.register_blueprint(user_bp, url_prefix='/user')
app.register_blueprint(order_bp, url_prefix='/order')
app.register_blueprint(chatty_bp, url_prefix='/chatty')
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

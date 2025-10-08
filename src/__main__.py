import os

from .database.enum import UserRole
from database_api import set_database
from . import app, IS_DEV, DATABASE_URL
from .database.schema import ItalcoUser
from .end_points import flask_session_authentication

from .end_points.orders import order_bp
from .end_points.schedule import schedule_bp
from .end_points.importation import import_bp
from .end_points.exportation import export_bp
from .end_points.users import user_bp, login_
from .end_points.users.seed import seed_users
from .end_points.transport import transport_bp
from .end_points.customer_group import customer_group_bp
from .end_points.delivery_group import delivery_group_bp
from .end_points.collection_point import collection_point_bp
from .end_points.service import service_bp, check_services_date
from .end_points.customer_rules import customer_rules_bp, check_customer_rules
from .end_points.geographic_zone import geographic_zone_bp, check_geographic_zone


@app.route('/login', methods=['POST'])
def login():
  return login_()


@app.route('/check-constraints', methods=['POST'])
@flask_session_authentication([UserRole.CUSTOMER])
def check_constraints(user: ItalcoUser):
  return {
    'status': 'ok',
    'dates': sorted(list(set(check_customer_rules(user)) & set(check_geographic_zone()) & set(check_services_date()))),
  }


app.register_blueprint(user_bp, url_prefix='/user')
app.register_blueprint(order_bp, url_prefix='/order')
app.register_blueprint(import_bp, url_prefix='/import')
app.register_blueprint(export_bp, url_prefix='/export')
app.register_blueprint(service_bp, url_prefix='/service')
app.register_blueprint(schedule_bp, url_prefix='/schedule')
app.register_blueprint(transport_bp, url_prefix='/transport')
app.register_blueprint(customer_rules_bp, url_prefix='/customer-rule')
app.register_blueprint(customer_group_bp, url_prefix='/customer-group')
app.register_blueprint(delivery_group_bp, url_prefix='/delivery-group')
app.register_blueprint(geographic_zone_bp, url_prefix='/geographic-zone')
app.register_blueprint(collection_point_bp, url_prefix='/collection-point')


if __name__ == '__main__':
  set_database(DATABASE_URL)
  if IS_DEV:
    seed_users()
  app.run(host='0.0.0.0', port=8080)

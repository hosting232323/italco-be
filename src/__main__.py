import subprocess

from api.settings import IS_DEV
from .database.schema import User
from .database.enum import UserRole
from .database.seed import seed_data
from database_api import set_database
from . import app, DATABASE_URL, PORT
from .end_points.users.session import flask_session_authentication

from .end_points.users import user_bp
from .end_points.orders import order_bp
from .end_points.checks import checks_bp
from .end_points.chatty import chatty_bp
from .end_points.service import service_bp
from .end_points.schedule import schedule_bp
from .end_points.exportation import export_bp
from .end_points.transport import transport_bp
from .end_points.pdf_importation import pdf_import_bp
from .end_points.customer_group import customer_group_bp
from .end_points.excel_importation import excel_import_bp
from .end_points.collection_point import collection_point_bp
from .end_points.service.constraint import check_services_date
from .end_points.customer_rules import customer_rules_bp, check_customer_rules
from .end_points.geographic_zone import geographic_zone_bp, check_geographic_zone


@app.route('/check-constraints', methods=['POST'])
@flask_session_authentication([UserRole.CUSTOMER])
def check_constraints(user: User):
  return {
    'status': 'ok',
    'dates': sorted(list(set(check_customer_rules(user)) & set(check_geographic_zone()) & set(check_services_date()))),
  }


app.register_blueprint(user_bp, url_prefix='/user')
app.register_blueprint(order_bp, url_prefix='/order')
app.register_blueprint(checks_bp, url_prefix='/checks')
app.register_blueprint(chatty_bp, url_prefix='/chatty')
app.register_blueprint(export_bp, url_prefix='/export')
app.register_blueprint(service_bp, url_prefix='/service')
app.register_blueprint(schedule_bp, url_prefix='/schedule')
app.register_blueprint(transport_bp, url_prefix='/transport')
app.register_blueprint(pdf_import_bp, url_prefix='/pdf-import')
app.register_blueprint(excel_import_bp, url_prefix='/excel-import')
app.register_blueprint(customer_rules_bp, url_prefix='/customer-rule')
app.register_blueprint(customer_group_bp, url_prefix='/customer-group')
app.register_blueprint(geographic_zone_bp, url_prefix='/geographic-zone')
app.register_blueprint(collection_point_bp, url_prefix='/collection-point')


set_database(DATABASE_URL)


if __name__ == '__main__':
  if not IS_DEV:
    print('Avvio in corso in modalità produzione...')
    subprocess.run(
      [
        'gunicorn',
        '-w',
        '4',
        '-b',
        f'127.0.0.1:{PORT}',
        '--access-logfile',
        '-',
        '--error-logfile',
        '-',
        'src.__main__:app',
      ]
    )
  else:
    print('Avvio in corso in modalità sviluppo...')
    seed_data()
    app.run(host='0.0.0.0', port=PORT)

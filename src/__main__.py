import os
from flask import jsonify

from . import app, IS_DEV
from database_api import set_database
from .end_points.order import order_bp
from .end_points.service import service_bp
from .end_points.importation import import_bp
from .end_points.exportation import export_bp
from .end_points.users import user_bp, login_
from .end_points.users.seed import seed_users
from .end_points.addressee import addressee_bp
from .end_points.delivery_group import delivery_group_bp
from .end_points.collection_point import collection_point_bp


@app.route('/login', methods=['POST'])
def login():
  return jsonify(login_())


app.register_blueprint(user_bp, url_prefix='/user')
app.register_blueprint(order_bp, url_prefix='/order')
app.register_blueprint(import_bp, url_prefix='/import')
app.register_blueprint(export_bp, url_prefix='/export')
app.register_blueprint(service_bp, url_prefix='/service')
app.register_blueprint(addressee_bp, url_prefix='/addressee')
app.register_blueprint(delivery_group_bp, url_prefix='/delivery-group')
app.register_blueprint(collection_point_bp, url_prefix='/collection-point')


if __name__ == '__main__':
  set_database(
    os.environ['DATABASE_URL'],
    'italco-be' if not IS_DEV else None
  )
  if IS_DEV:
    seed_users()
  app.run(host='0.0.0.0', port=8080)

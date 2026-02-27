import os
from flask_cors import CORS
from flask import Flask, send_from_directory

from api.settings import IS_DEV
from database_api.backup import db_backup
from api import swagger_decorator, PrefixMiddleware


allowed_origins = [
  'https://ares-logistics.it',
  'https://www.ares-logistics.it',
]


PORT = int(os.environ.get('PORT', 8080))
DATABASE_URL = os.environ['DATABASE_URL']
EURONICS_API_PASSWORD = os.environ.get('EURONICS_API_PASSWORD', None)
POSTGRES_BACKUP_DAYS = int(os.environ.get('POSTGRES_BACKUP_DAYS', 14))
STATIC_FOLDER = os.environ.get(
  'STATIC_FOLDER', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static')
)


app = Flask(__name__, static_folder=STATIC_FOLDER, template_folder='../templates')


API_PREFIX = os.environ.get('API_PREFIX', None)
if API_PREFIX:
  app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefix=f'/{API_PREFIX}')


if IS_DEV:
  CORS(app)
else:
  CORS(app, origins=allowed_origins)


@app.route('/', methods=['GET'])
def index():
  return 'Hello World', 200


@app.route('/<path:filename>', methods=['GET'])
def serve_image(filename):
  return send_from_directory(STATIC_FOLDER, filename)


@app.route('/internal-backup', methods=['GET'])
@swagger_decorator
def trigger_backup():
  return db_backup(DATABASE_URL, STATIC_FOLDER, 'local', 'backup')

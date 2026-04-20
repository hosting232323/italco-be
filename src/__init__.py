import os
from flask_cors import CORS
from flask import Flask, send_from_directory

from api.settings import IS_DEV
from .checks import trigger_checks
from database_api.backup import db_backup
from api.storage.local import folder_backup
from api import swagger_decorator, error_catching_decorator, PrefixMiddleware


allowed_origins = [
  'https://ares-logistics.it',
  'https://www.ares-logistics.it',
]


DATABASE_URL = os.environ['DATABASE_URL']
LOCAL_PORT = int(os.environ.get('LOCAL_PORT', 8080))
BACKUP_FOLDER = os.environ.get('BACKUP_FOLDER', None)
RESTIC_PASSWORD = os.environ.get('RESTIC_PASSWORD', None)
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
@error_catching_decorator
def serve_image(filename):
  return send_from_directory(STATIC_FOLDER, filename)


@app.route('/internal-backup', methods=['GET'])
@error_catching_decorator
@swagger_decorator
def trigger_backup():
  return db_backup(DATABASE_URL, os.path.join(BACKUP_FOLDER, 'postgres-backup'), 'local')


@app.route('/folder-backup', methods=['GET'])
@error_catching_decorator
@swagger_decorator
def trigger_backup_folder():
  return folder_backup(
    os.path.join(BACKUP_FOLDER, 'folder-backup'), os.path.join(STATIC_FOLDER, 'photos', 'prod'), RESTIC_PASSWORD
  )


@app.route('/checks', methods=['GET'])
@error_catching_decorator
@swagger_decorator
def checks_endpoint():
  return trigger_checks(STATIC_FOLDER)

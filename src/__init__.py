import os
import threading
from flask import Flask
from flask_cors import CORS

from api.settings import IS_DEV
from .checks import trigger_checks
from api.storage import folder_backup
from database_api.backup import db_backup
from api import swagger_decorator, error_catching_decorator, PrefixMiddleware


allowed_origins = [
  'https://ares-logistics.it',
  'https://www.ares-logistics.it',
]


DATABASE_URL = os.environ['DATABASE_URL']
LOCAL_PORT = int(os.environ.get('LOCAL_PORT', 8080))
BACKUP_FOLDER = os.environ.get('BACKUP_FOLDER', None)
EURONICS_API_PASSWORD = os.environ.get('EURONICS_API_PASSWORD', None)
POSTGRES_BACKUP_DAYS = int(os.environ.get('POSTGRES_BACKUP_DAYS', 14))
STATIC_FOLDER = os.environ.get(
  'STATIC_FOLDER', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static')
)


app = Flask(__name__, template_folder='../templates')


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


@app.route('/internal-backup', methods=['GET'])
@error_catching_decorator
@swagger_decorator
def trigger_backup():
  threading.Thread(
    target=db_backup,
    args=(DATABASE_URL, BACKUP_FOLDER, 'server', 'postgres-backup'),
    daemon=True,
  ).start()

  return {'status': 'ok', 'message': 'Operazione completata con successo!'}


@app.route('/folder-backup', methods=['GET'])
@error_catching_decorator
@swagger_decorator
def trigger_backup_folder():
  if folder_backup is None:
    return {
      'status': 'error',
      'message': 'folder_backup is not available in the installed api.storage.local package.',
    }, 503

  threading.Thread(
    target=folder_backup,
    args=(os.path.join(STATIC_FOLDER, 'photos', 'prod'), 'server'),
    daemon=True,
  ).start()

  return {'status': 'ok', 'message': 'Operazione completata con successo!'}


@app.route('/checks', methods=['GET'])
@error_catching_decorator
@swagger_decorator
def checks_endpoint():
  return trigger_checks(STATIC_FOLDER)

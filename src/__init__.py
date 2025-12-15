import os
import shutil
from flask_cors import CORS
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, send_from_directory

from database_api.backup import data_export
from api import swagger_decorator, PrefixMiddleware


allowed_origins = [
  'https://ares-logistics.it',
  'https://www.ares-logistics.it',
]


load_dotenv()
PORT = int(os.environ.get('PORT', 8080))
DATABASE_URL = os.environ['DATABASE_URL']
IS_DEV = int(os.environ.get('IS_DEV', 1)) == 1
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'default')
STATIC_FOLDER = os.environ.get('STATIC_FOLDER', '../static')
POSTGRES_BACKUP_DAYS = int(os.environ.get('POSTGRES_BACKUP_DAYS', 14))


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


@app.route('/<path:filename>')
def serve_image(filename):
  return send_from_directory(STATIC_FOLDER, filename)


def safe_copy_to_remote(src, dst):
  with open(src, 'rb') as fsrc, open(dst, 'wb') as fdst:
    shutil.copyfileobj(fsrc, fdst)
  os.remove(src)


@swagger_decorator
@app.route('/internal-backup', methods=['POST'])
def trigger_backup():
  backup_path = os.path.join(STATIC_FOLDER, 'backup')
  if not os.path.exists(backup_path):
    return {'status': 'ko', 'message': 'Cartella di backup non trovata'}

  zip_filename = data_export(DATABASE_URL)
  src_path = zip_filename
  dest_path = os.path.join(backup_path, src_path)
  safe_copy_to_remote(src_path, dest_path)

  manage_local_backups(backup_path)
  print(f'[{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}] Backup eseguito!')
  return {'status': 'ok', 'message': 'Backup eseguito con successo'}


def manage_local_backups(local_folder: str):
  backups = [
    os.path.join(local_folder, f)
    for f in os.listdir(local_folder)
    if os.path.isfile(os.path.join(local_folder, f))
  ]

  backups.sort()  
  if len(backups) > POSTGRES_BACKUP_DAYS:
    for path in backups[: len(backups) - POSTGRES_BACKUP_DAYS]:
      os.remove(path)

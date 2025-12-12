import os
from flask_cors import CORS
from datetime import datetime
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
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


@swagger_decorator
@app.route('/internal-backup', methods=['POST'])
def trigger_backup():
  zip_filename = data_export(DATABASE_URL)
  safe_name = secure_filename(zip_filename)
  
  os.makedirs(STATIC_FOLDER, exist_ok=True)
  dest_path = os.path.join(STATIC_FOLDER, safe_name)

  os.rename(zip_filename, dest_path)
  manage_local_backups(STATIC_FOLDER)
  
  print(f'[{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}] Backup eseguito!')


def manage_local_backups(local_folder: str):
  backups = [
    os.path.join(local_folder, f)
    for f in os.listdir(local_folder)
    if os.path.isfile(os.path.join(local_folder, f))
  ]
    
  backups.sort()
    
  backup_days = int(os.environ.get('POSTGRES_BACKUP_DAYS', 14))

  if len(backups) > backup_days:
    files_to_delete = backups[: len(backups) - backup_days]
    for path in files_to_delete:
      os.remove(path)


@app.route('/<path:filename>')
def serve_image(filename):
  return send_from_directory(STATIC_FOLDER, filename)

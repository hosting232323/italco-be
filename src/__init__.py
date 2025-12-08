import os
from flask_cors import CORS
from dotenv import load_dotenv
from flask import Flask, send_from_directory

from database_api.backup import db_backup
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
  return db_backup(DATABASE_URL, PROJECT_NAME)


@app.route('/<path:filename>')
def serve_image(filename):
  return send_from_directory(STATIC_FOLDER, filename)

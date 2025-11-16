import os
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv

from api import swagger_decorator
from database_api.backup import db_backup


allowed_origins = [
  'https://ares-logistics.it',
  'https://www.ares-logistics.it',
]

load_dotenv()
IS_DEV = int(os.environ.get('IS_DEV', 1)) == 1
PORT = int(os.environ.get('PORT', 8080))
DATABASE_URL = os.environ['DATABASE_URL']
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'default')
app = Flask(__name__, static_folder='../static', template_folder='../templates')

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

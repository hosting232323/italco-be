import os
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv
from flask_swagger_ui import get_swaggerui_blueprint

from api import swagger_decorator
from database_api.backup import db_backup


allowed_origins = [
  'https://ares-logistics.it',
  'https://www.ares-logistics.it',
]

load_dotenv()
IS_DEV = int(os.environ.get('IS_DEV', 1)) == 1
DATABASE_URL = os.environ['DATABASE_URL']
app = Flask(__name__, static_folder='../static', template_folder='../templates')

# Swagger da eliminare?
app.register_blueprint(
  get_swaggerui_blueprint('/swagger', '/static/swagger.json', config={'app_name': 'Italco'}), url_prefix='/swagger'
)

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
  return db_backup(DATABASE_URL, 'italco-be')

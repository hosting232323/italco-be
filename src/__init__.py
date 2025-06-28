import os
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv
from flask_swagger_ui import get_swaggerui_blueprint

from api import swagger_decorator, internal_backup


allowed_origins = [
  # add allowed origins
]

load_dotenv()
IS_DEV = int(os.environ.get('IS_DEV', 1)) == 1
app = Flask(__name__, static_folder='../static', template_folder='../templates')

# Swagger da eliminare?
app.register_blueprint(
  get_swaggerui_blueprint(
    '/swagger',
    '/static/swagger.json',
    config={'app_name': 'Italco'}
  ), url_prefix='/swagger'
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
  return internal_backup('italco-be')

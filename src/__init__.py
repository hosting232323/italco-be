import os
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv
from flask_swagger_ui import get_swaggerui_blueprint


allowed_origins = [
  # add allowed origins
]

load_dotenv()
IS_DEV = int(os.environ.get('IS_DEV', 1)) == 1
app = Flask(__name__, static_folder='../static')

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

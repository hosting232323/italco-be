import os
from flask import Flask
from flask_cors import CORS

from api.settings import IS_DEV
from .checks import trigger_checks
from api.storage import folder_backup
from database_api.backup import db_backup
from api import swagger_decorator, register_flask_hooks, PrefixMiddleware


allowed_origins = [
  'https://ares-logistics.it',
  'https://www.ares-logistics.it',
]

# Origin aggiuntive per gli ambienti che non stanno sul dominio di produzione
# (tipicamente il frontend di test). Vanno elencate esplicitamente: con
# supports_credentials=True una CORS che riflette qualunque origin lascia che un
# sito qualsiasi guidi l'API con la sessione di chi lo visita.
EXTRA_ALLOWED_ORIGINS = [
  origin.strip() for origin in os.environ.get('EXTRA_ALLOWED_ORIGINS', '').split(',') if origin.strip()
]


DATABASE_URL = os.environ['DATABASE_URL']
LOCAL_PORT = int(os.environ.get('LOCAL_PORT', 8080))
EURONICS_API_PASSWORD = os.environ.get('EURONICS_API_PASSWORD', None)

# Leva manuale: nessuna colonna, nessuna migration. Si alza a mano (commit o
# variabile d'ambiente) solo quando una build vecchia dell'app corrieri va
# davvero bloccata, non a ogni release - vedi CI_PIPELINE_IID in
# gitlab/build-android.yml e build-ios.yml del repo delivery-app, che e' lo
# stesso numero letto da PackageInfo.buildNumber nell'app.
DELIVERY_APP_MIN_BUILD_NUMBER = os.environ.get('DELIVERY_APP_MIN_BUILD_NUMBER', None)
STATIC_FOLDER = os.environ.get(
  'STATIC_FOLDER', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static')
)
app = Flask(__name__, template_folder='../templates')


API_PREFIX = os.environ.get('API_PREFIX', None)
if API_PREFIX:
  app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefix=f'/{API_PREFIX}')


if IS_DEV and not EXTRA_ALLOWED_ORIGINS:
  # Solo sviluppo locale, dove l'origin del frontend non e' prevedibile.
  # Negli ambienti deployati con IS_DEV=1 (il test) va valorizzata
  # EXTRA_ALLOWED_ORIGINS, cosi' anche li' la lista diventa esplicita.
  CORS(app, supports_credentials=True)
else:
  CORS(app, origins=allowed_origins + EXTRA_ALLOWED_ORIGINS, supports_credentials=True)


register_flask_hooks(app, STATIC_FOLDER, user_log_field='nickname')


@app.route('/', methods=['GET'])
def index():
  return 'Hello World', 200


@app.route('/internal-backup', methods=['GET'])
@swagger_decorator
def trigger_backup():
  db_backup(DATABASE_URL, server=True)
  return {'status': 'ok', 'message': 'Operazione completata con successo!'}


@app.route('/folder-backup', methods=['GET'])
@swagger_decorator
def trigger_backup_folder():
  folder_backup(os.path.join(STATIC_FOLDER, 'prod'), server=True)
  return {'status': 'ok', 'message': 'Backup avviato in background!'}


@app.route('/checks', methods=['GET'])
@swagger_decorator
def checks_endpoint():
  return trigger_checks(STATIC_FOLDER)


@app.route('/delivery-app/min-version', methods=['GET'])
def delivery_app_min_version():
  # Chiamata all'avvio, prima del login: nessuna autenticazione. Un valore
  # non impostato o non numerico significa "nessuna soglia", non un errore -
  # l'app dei corrieri non deve mai bloccarsi per una svista di configurazione.
  try:
    min_build_number = int(DELIVERY_APP_MIN_BUILD_NUMBER)
  except (TypeError, ValueError):
    min_build_number = None
  return {'status': 'ok', 'min_build_number': min_build_number}

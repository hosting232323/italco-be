import inspect
import logging
import os
import time
from flask import Flask, request
from flask_cors import CORS

from api.settings import IS_DEV, TELEGRAM_TOKEN
from api.telegram import send_telegram_message
from .checks import trigger_checks
from .rate_limit import client_ip, rate_limited
from api.storage import folder_backup
from database_api.backup import db_backup
from api import swagger_decorator, register_flask_hooks, PrefixMiddleware


allowed_origins = [
  'https://hubstra.it',
  'https://www.hubstra.it',
]
DATABASE_URL = os.environ['DATABASE_URL']
LOCAL_PORT = int(os.environ.get('LOCAL_PORT', 8080))
EURONICS_API_PASSWORD = os.environ.get('EURONICS_API_PASSWORD', None)

# Istanza OSRM per matrice durate (/table) e ottimizzazione borderò (/trip). Il
# default e' il demo pubblico, senza SLA ne' rate limit documentati: in produzione
# va puntata a un'istanza self-hosted. Vuoto (variabile CI non valorizzata) = default.
OSRM_BASE_URL = (os.environ.get('OSRM_BASE_URL') or 'https://router.project-osrm.org').rstrip('/')

# Leva manuale: nessuna colonna, nessuna migration. Si alza a mano (commit o
# variabile d'ambiente) solo quando una build vecchia dell'app corrieri va
# davvero bloccata, non a ogni release - vedi CI_PIPELINE_IID in
# gitlab/build-android.yml e build-ios.yml del repo delivery-app, che e' lo
# stesso numero letto da PackageInfo.buildNumber nell'app.
#
# Compatibilità della soglia versione delivery app. Le app già distribuite
# chiamano l'endpoint senza ?platform=: per loro si usa la variabile legacy
# DELIVERY_APP_MIN_BUILD_NUMBER. Le versioni aggiornate passano la piattaforma
# e usano le variabili specifiche.
#
# Soglia per piattaforma, l'endpoint /delivery-app/min-version la sceglie in
# base a ?platform=:
#  - iOS (DELIVERY_APP_MIN_BUILD_NUMBER_IOS): soglia di routine. Le build
#    TestFlight scadono a 90 giorni e la pipeline schedulata ne carica una
#    nuova ogni ~60, quindi senza blocco un corriere che non aggiorna resta
#    senza app.
#  - Android (DELIVERY_APP_MIN_BUILD_NUMBER_ANDROID): di norma NON impostata.
#    Le build Play non scadono e Play aggiorna da solo. Si valorizza solo per
#    forzare un rollout d'emergenza (bug grave) e si rimuove appena Play ha
#    propagato l'aggiornamento - occhio che il rollout Play e' graduale,
#    alzarla puo' bloccare chi non ha ancora ricevuto la nuova build.
DELIVERY_APP_MIN_BUILD_NUMBER_IOS = os.environ.get('DELIVERY_APP_MIN_BUILD_NUMBER_IOS', None)
DELIVERY_APP_MIN_BUILD_NUMBER_ANDROID = os.environ.get('DELIVERY_APP_MIN_BUILD_NUMBER_ANDROID', None)
DELIVERY_APP_MIN_BUILD_NUMBER = os.environ.get('DELIVERY_APP_MIN_BUILD_NUMBER', None)
STATIC_FOLDER = os.environ.get(
  'STATIC_FOLDER', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static')
)
app = Flask(__name__, template_folder='../templates')
logger = logging.getLogger(__name__)


API_PREFIX = os.environ.get('API_PREFIX', None)
if API_PREFIX:
  app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefix=f'/{API_PREFIX}')


if IS_DEV:
  # Sviluppo e ambiente di test: il frontend puo' girare su host diversi.
  CORS(app, supports_credentials=True)
else:
  CORS(app, origins=allowed_origins, supports_credentials=True)


# Percorsi di cui il log tiene solo metodo, path, utente ed esito, senza i body:
# login, refresh e gestione utenti portano credenziali e posizioni dei corrieri,
# il tracking pubblico e la richiesta demo portano dati di chi non e' un utente,
# i rapporti d'errore dell'app corrieri sono aperti e il loro contenuto e' gia'
# loggato in forma troncata dall'endpoint.
LOG_BODY_EXCLUDED_PREFIXES = ('/user', '/order/public', '/demo-request', '/delivery-app')


def _register_log_hooks(flask_app):
  # generic-lib non e' fissata a una versione: body_excluded_prefixes esiste
  # solo dalle versioni che lo introducono. Con una generic-lib piu' vecchia
  # l'app deve comunque partire, con il log di prima.
  if 'body_excluded_prefixes' in inspect.signature(register_flask_hooks).parameters:
    return register_flask_hooks(
      flask_app,
      STATIC_FOLDER,
      user_log_field='nickname',
      body_excluded_prefixes=LOG_BODY_EXCLUDED_PREFIXES,
    )

  logger.warning('generic-lib senza body_excluded_prefixes: i body di %s restano nel log', LOG_BODY_EXCLUDED_PREFIXES)
  return register_flask_hooks(flask_app, STATIC_FOLDER, user_log_field='nickname')


_register_log_hooks(app)


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
  #
  # I client aggiornati chiedono la soglia della propria piattaforma.
  # I client gia' distribuiti non mandano platform: manteniamo per loro la
  # soglia legacy unica, cosi' possono essere aggiornati prima di separare le
  # configurazioni iOS e Android.
  platform = request.args.get('platform')
  if platform is None:
    raw_min_build_number = DELIVERY_APP_MIN_BUILD_NUMBER
  elif platform.lower() == 'android':
    raw_min_build_number = DELIVERY_APP_MIN_BUILD_NUMBER_ANDROID
  else:
    raw_min_build_number = DELIVERY_APP_MIN_BUILD_NUMBER_IOS
  try:
    min_build_number = int(raw_min_build_number)
  except (TypeError, ValueError):
    min_build_number = None
  build_number = request.args.get('build_number')
  if platform in {'android', 'ios'} and build_number and build_number.isdigit():
    app.logger.info(
      'delivery-app version check platform=%s build=%s minimum=%s',
      platform,
      build_number,
      min_build_number,
    )
  return {'status': 'ok', 'min_build_number': min_build_number}


# Tetti sui campi del rapporto: l'endpoint e' aperto (un errore puo' capitare
# prima del login) quindi niente che arrivi da fuori finisce nel log senza limite.
DELIVERY_APP_ERROR_REPORT_FIELDS = {
  'message': 1000,
  'stack': 6000,
  'source': 100,
  'occurred_at': 40,
  'app_version': 40,
  'commit': 64,
  'build_number': 20,
  'platform': 20,
}


# Anti-spam della notifica Telegram: l'endpoint e' aperto, quindi lo stesso
# errore avvisa una volta sola per finestra e in totale ci sono al massimo
# DELIVERY_APP_ERROR_ALERTS_PER_HOUR avvisi all'ora. Il log li ha comunque tutti.
DELIVERY_APP_ERROR_ALERT_WINDOW_SECONDS = 3600
DELIVERY_APP_ERROR_ALERTS_PER_HOUR = 10
# Tetto per IP ai rapporti accettati: oltre, 429 senza scrivere nel log. Largo,
# perche' piu' corrieri possono uscire dallo stesso IP (rete mobile condivisa).
DELIVERY_APP_ERROR_REPORTS_PER_HOUR_PER_IP = 60
_delivery_app_error_alerts = {}


def _notify_delivery_app_error(report):
  if IS_DEV or not TELEGRAM_TOKEN:
    return

  now = time.monotonic()
  for key, sent_at in list(_delivery_app_error_alerts.items()):
    if now - sent_at > DELIVERY_APP_ERROR_ALERT_WINDOW_SECONDS:
      del _delivery_app_error_alerts[key]
  key = (report['app_version'], report['build_number'], report['message'], report['stack'].split(' | ')[0])
  if key in _delivery_app_error_alerts or len(_delivery_app_error_alerts) >= DELIVERY_APP_ERROR_ALERTS_PER_HOUR:
    return
  _delivery_app_error_alerts[key] = now

  detail = (report['message'] + chr(10) + report['stack'].replace(' | ', chr(10))).replace('```', "'''")
  send_telegram_message(
    '*📱 Errore app corrieri*\n'
    f'{report["platform"]} · v{report["app_version"]} · build {report["build_number"]} · {report["commit"][:8]}\n'
    f'```\n{detail}\n```'
  )


@app.route('/delivery-app/error-report', methods=['POST'])
def delivery_app_error_report():
  # Rapporto di un errore non gestito dell'app corrieri (ErrorReporter in
  # delivery-app). Nessuna autenticazione, come /delivery-app/min-version, e
  # nessuna tabella: finisce nel log del servizio, una riga per rapporto.
  if rate_limited(client_ip(), 'delivery-app-error-report', DELIVERY_APP_ERROR_REPORTS_PER_HOUR_PER_IP):
    return {'status': 'ko', 'message': 'Troppi rapporti, riprova più tardi'}, 429

  body = request.get_json(silent=True)
  if not isinstance(body, dict):
    return {'status': 'ko', 'message': 'Rapporto non valido'}, 400

  report = {
    field: str(body.get(field, ''))[:limit].replace(chr(10), ' | ')
    for field, limit in DELIVERY_APP_ERROR_REPORT_FIELDS.items()
  }
  _notify_delivery_app_error(report)
  logger.error(
    'delivery-app error report: platform=%(platform)s version=%(app_version)s build=%(build_number)s '
    'commit=%(commit)s source=%(source)s at=%(occurred_at)s message=%(message)s stack=%(stack)s',
    report,
  )
  return {'status': 'ok'}

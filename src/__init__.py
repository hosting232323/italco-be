import os
import shutil
from flask_cors import CORS
from datetime import datetime
from flask import Flask, send_from_directory

from api.settings import IS_DEV
from database_api.backup import data_export
from api import swagger_decorator, PrefixMiddleware

from api.telegram import send_telegram_message

from database_api import Session
from .database.schema import (
  Order,
  Product,
  ServiceUser,
  Schedule,
)


allowed_origins = [
  'https://ares-logistics.it',
  'https://www.ares-logistics.it',
]


PORT = int(os.environ.get('PORT', 8080))
DATABASE_URL = os.environ['DATABASE_URL']
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


@app.route('/check-mismatch', methods=['GET'])
def check_mismatch():
  with Session() as session:
    # --- Schedule senza ScheduleItem o DeliveryGroup ---
    schedules = session.query(Schedule).all()
    schedule_issues = []
    for sched in schedules:
      missing = []
      if not sched.schedule_item:
        missing.append('ScheduleItem')
      if not sched.delivery_group:
        missing.append('DeliveryGroup')
      if missing:
        schedule_issues.append({
          "schedule_id": sched.id,
          "date": sched.date.isoformat(),
          "missing": missing,
          "transport_id": sched.transport_id,
        })

    # --- Ordini senza utenti associati ---
    orders_no_user = (
      session.query(Order)
      .outerjoin(Product)
      .outerjoin(ServiceUser)
      .filter(ServiceUser.id == None)
      .all()
    )
    orders_no_user_result = [
      {"order_id": o.id, "addressee": o.addressee, "status": o.status.value}
      for o in orders_no_user
    ]

    # --- Ordini senza prodotti ---
    orders_no_product = (
      session.query(Order)
      .outerjoin(Product)
      .filter(Product.id == None)
      .all()
    )
    orders_no_product_result = [
      {"order_id": o.id, "addressee": o.addressee, "status": o.status.value}
      for o in orders_no_product
    ]

  send_telegram_message(
    "*📊 Report Check Mismatch*\n\n"
    f"*Schedules con problemi:* {schedule_issues}\n"
    f"*Ordini senza utente:* {orders_no_user_result}\n"
    f"*Ordini senza prodotti:* {orders_no_product_result}\n\n"
  )
  return { 'status': 'ok' }

@swagger_decorator
@app.route('/internal-backup', methods=['POST'])
def trigger_backup():
  backup_path = os.path.join(STATIC_FOLDER, 'backup')
  if not os.path.exists(backup_path):
    return {'status': 'ko', 'message': 'Cartella di backup non trovata'}

  zip_filename = data_export(DATABASE_URL)
  safe_copy_to_remote(zip_filename, os.path.join(backup_path, zip_filename))
  manage_local_backups(backup_path)
  print(f'[{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}] Backup eseguito!')
  return {'status': 'ok', 'message': 'Backup eseguito con successo'}


def safe_copy_to_remote(src, dst):
  with open(src, 'rb') as fsrc, open(dst, 'wb') as fdst:
    shutil.copyfileobj(fsrc, fdst)
  os.remove(src)


def manage_local_backups(local_folder: str):
  backups = [
    os.path.join(local_folder, file)
    for file in os.listdir(local_folder)
    if os.path.isfile(os.path.join(local_folder, file))
  ]

  backups.sort()
  if len(backups) > POSTGRES_BACKUP_DAYS:
    for path in backups[: len(backups) - POSTGRES_BACKUP_DAYS]:
      os.remove(path)

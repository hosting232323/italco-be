import os
import shutil
from flask_cors import CORS
from datetime import datetime
from flask import Flask, send_from_directory

from api.settings import IS_DEV
from database_api.backup import data_export
from api import swagger_decorator, PrefixMiddleware


allowed_origins = [
  'https://ares-logistics.it',
  'https://www.ares-logistics.it',
]


PORT = int(os.environ.get('PORT', 8080))
DATABASE_URL = os.environ['DATABASE_URL']
POSTGRES_BACKUP_DAYS = int(os.environ.get('POSTGRES_BACKUP_DAYS', 14))
STATIC_FOLDER = os.environ.get(
  'STATIC_FOLDER', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static')
)


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

import pdfplumber
import re

@app.route('/file-read', methods=['POST'])
def file_read():
  testo = estrai_testo_pdf('tommaso tedesco.pdf')
  return parse_bolla(testo)


def estrai_testo_pdf(percorso_pdf):
  testo = ""
  with pdfplumber.open(percorso_pdf) as pdf:
    for pagina in pdf.pages:
      testo += pagina.extract_text() + "\n"
  return testo


def parse_bolla(testo):
    dati = {}

    dati["numero_bolla"] = re.search(r"BOLLA DI SERVIZIO E CONSEGNA Numero:\s*(\d+)", testo)
    dati["numero_bolla"] = dati["numero_bolla"].group(1) if dati["numero_bolla"] else None

    dati["data_emissione"] = re.search(r"Data emissione.*?\n(\d{2}/\d{2}/\d{4})", testo)
    dati["data_emissione"] = dati["data_emissione"].group(1) if dati["data_emissione"] else None

    dati["luogo_emissione"] = re.search(r"Data emissione Luogo di emissione\n.*?\s+(\w+)", testo)
    dati["luogo_emissione"] = dati["luogo_emissione"].group(1) if dati["luogo_emissione"] else None

    dati["destinatario"] = re.search(r"Destinatario:\s*(.+)", testo)
    dati["destinatario"] = dati["destinatario"].group(1).strip() if dati["destinatario"] else None

    dati["indirizzo_destinatario"] = re.search(r"Destinatario:.*\n(.+)", testo)
    dati["indirizzo_destinatario"] = dati["indirizzo_destinatario"].group(1).strip() if dati["indirizzo_destinatario"] else None

    dati["telefono"] = re.search(r"Tel - Cell:\s*([\d]+)", testo)
    dati["telefono"] = dati["telefono"].group(1) if dati["telefono"] else None

    articolo = re.search(
        r"ARTICOLI E SERVIZI RICHIESTI.*?\n(\d+)\s+(.+?)\s+(\d+)\s+CONSEGNA",
        testo,
        re.S
    )

    if articolo:
        dati["codice_articolo"] = articolo.group(1)
        dati["descrizione_articolo"] = articolo.group(2).strip()
        dati["quantita"] = articolo.group(3)
    else:
        dati["codice_articolo"] = None
        dati["descrizione_articolo"] = None
        dati["quantita"] = None

    dati["data_consegna"] = re.search(r"Data consegna:\s*(\d{2}/\d{2}/\d{4})", testo)
    dati["data_consegna"] = dati["data_consegna"].group(1) if dati["data_consegna"] else None

    return dati


@swagger_decorator
@app.route('/internal-backup', methods=['POST'])
def trigger_backup():
  backup_path = os.path.join(STATIC_FOLDER, 'backup')
  if not os.path.exists(backup_path):
    return {'status': 'ko', 'error': 'Cartella di backup non trovata'}

  zip_filename = data_export(DATABASE_URL)
  safe_copy_to_remote(zip_filename, os.path.join(backup_path, zip_filename))
  manage_local_backups(backup_path)
  print(f'[{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}] Backup eseguito!')
  return {'status': 'ok', 'error': 'Backup eseguito con successo'}


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

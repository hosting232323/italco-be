import os
import shutil
from flask_cors import CORS
from datetime import datetime
from flask import Flask, send_from_directory

from api.settings import IS_DEV
from database_api.backup import data_export
from api import swagger_decorator, PrefixMiddleware

from .end_points.geographic_zone import get_cap_by_name


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
  testo = estrai_testo_pdf('doc (28)_merged-1.pdf')
  parse_bolla(testo)
  return {'status': 'ok'}


def estrai_testo_pdf(percorso_pdf):
  testo = ""
  with pdfplumber.open(percorso_pdf) as pdf:
    for pagina in pdf.pages:
      testo += pagina.extract_text() + "\n"
  return testo

from database_api.operations import create
from .database.schema import Order
from .database.enum import OrderStatus, OrderType

def parse_bolla(testo):
  m_addressee = re.search(r"Destinatario:\s*(.+)", testo)
  addressee = m_addressee.group(1).strip() if m_addressee else None
  
  m_addressee_contact = re.search(r"Tel - Cell:\s*(\d+)", testo)
  addressee_contact = m_addressee_contact.group(1).strip() if m_addressee_contact else None
  
  address = None
  if addressee:
    m_address = re.search(r"Destinatario:.*\n(.+)", testo)
    if m_address:
      address = re.sub(r"Città\s*:\s*.+", "", m_address.group(1).strip()).strip()
      
      cities = re.findall(r"Città\s*:\s*(.+)", testo)
      city = cities[1].strip() if len(cities) > 1 else (cities[0].strip() if cities else None)
      city = re.sub(r"\bnd\b", "", city, flags=re.IGNORECASE).strip()
      
  m_dpc = re.search(r"Data consegna:\s*(\d{2}/\d{2}/\d{4})", testo)
  dpc = datetime.strptime(m_dpc.group(1).strip(), "%d/%m/%Y").date() if m_dpc else None
  
  create(Order, {
    "status": OrderStatus.PENDING,
    "type": OrderType.DELIVERY,
    "addressee": addressee,
    "address": address,
    "addressee_contact": addressee_contact,
    "cap": get_cap_by_name(city),
    "dpc": dpc,
    "drc": datetime.now()
  })

  # righe = [riga.strip() for riga in testo.strip().split("\n") if riga.strip()]
  # dati_articoli = []

  # inizio_tabella = None
  # for i, riga in enumerate(righe):
  #   if "Articolo" in riga and "Modello" in riga:
  #     inizio_tabella = i + 1
  #     break

  # if inizio_tabella is not None:
  #   for riga in righe[inizio_tabella:]:
  #     match = re.match(r"(\d+)\s+(\S+)\s+(.+?)\s+(\d+)\s+(.+)", riga)
  #     if match:
  #       codice, modello, descrizione, quantita, servizio = match.groups()
  #       dati_articoli.append({
  #         "articolo": codice,
  #         "modello": modello,
  #         "descrizione": descrizione.strip(),
  #         "quantita": quantita,
  #         "servizio": servizio.strip()
  #       })
        
  # data_consegna = re.search(r"Data consegna", testo)
  # dati["data_consegna"] = data_consegna.group(1) if data_consegna else None


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

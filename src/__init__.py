import os
import shutil
from flask_cors import CORS
from datetime import datetime
from flask import Flask, send_from_directory

from api.settings import IS_DEV
from database_api.backup import data_export
from api import swagger_decorator, PrefixMiddleware

from .end_points.geographic_zone import get_cap_by_name

import re
import pdfplumber
from database_api.operations import create
from .database.schema import Order, Product
from .database.enum import OrderStatus, OrderType


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


@app.route('/file-read', methods=['POST'])
def file_read():
  testo = ''
  
  with pdfplumber.open('doc (28)_merged-1.pdf') as pdf:
    for pagina in pdf.pages:
      testo += pagina.extract_text() + '\n'
    order: Order = pdf_create_order(testo)
    pdf_create_product(pagina.extract_tables(), order.id)
  # parse_bolla(testo)

  return {'status': 'ok'}


def pdf_create_product(tables, order_id: int):
  for table in tables:
    header = table[0]
    if header == [
        'Articolo',
        'Modello',
        'Tipologia - Descrizione',
        'Quantità - Peso Jg',
        'Servizio'
    ]:
      for row in table[1:]:
        quantita = None
        peso = None

        if row[3]:
          parti = row[3].split()
          quantita = parti[0]
          if len(parti) > 1:
            peso = parti[1]

        create(Product, {
          'name': f'{row[0]} {row[1]} {row[2]}',
          'order_id': order_id,
          'service_user_id': 3,
          'collection_point_id': 3
        })
        # articolo = {
        #   'articolo': row[0],
        #   'modello': row[1],
        #   'descrizione': row[2],
        #   'quantita': int(quantita) if quantita else None,
        #   'peso_jg': float(peso) if peso else None,
        #   'servizio': row[4],
        # }


def pdf_create_order(testo):
  m_addressee = re.search(r'Destinatario:\s*(.+)', testo)
  addressee = m_addressee.group(1).strip() if m_addressee else None

  m_addressee_contact = re.search(r'Tel - Cell:\s*(\d+)', testo)
  addressee_contact = m_addressee_contact.group(1).strip() if m_addressee_contact else None

  address = None
  if addressee:
    m_address = re.search(r'Destinatario:.*\n(.+)', testo)
    if m_address:
      address = re.sub(r'Città\s*:\s*.+', '', m_address.group(1).strip()).strip()

      cities = re.findall(r'Città\s*:\s*(.+)', testo)
      city = cities[1].strip() if len(cities) > 1 else (cities[0].strip() if cities else None)
      city = re.sub(r'\bnd\b', '', city, flags=re.IGNORECASE).strip()

  m_dpc = re.search(r'Data consegna:\s*(\d{2}/\d{2}/\d{4})', testo)
  dpc = datetime.strptime(m_dpc.group(1).strip(), '%d/%m/%Y').date() if m_dpc else None

  return create(
    Order,
    {
      'status': OrderStatus.PENDING,
      'type': OrderType.DELIVERY,
      'addressee': addressee,
      'address': address,
      'addressee_contact': addressee_contact,
      'cap': get_cap_by_name(city),
      'dpc': dpc,
      'drc': datetime.now(),
    },
  )


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

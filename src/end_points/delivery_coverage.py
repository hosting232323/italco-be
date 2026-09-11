from datetime import datetime

from sqlalchemy import asc
from sqlalchemy.orm import joinedload
from flask import Blueprint, request

from database_api import Session
from ..database.enum import UserRole
from . import flask_session_authentication
from database_api.operations import create, create_bulk, delete, delete_bulk, update, get_by_id
from ..database.schema import Transport, DeliveryCoverageEntry, DeliveryCoverageCap


delivery_coverage_bp = Blueprint('delivery_coverage_bp', __name__)

# Admin e operatori gestiscono la copertura; il super admin che opera in una
# company passa comunque, come ovunque (bypass in flask_session_authentication).
COVERAGE_ROLES = [UserRole.ADMIN, UserRole.OPERATOR]


def _parse_time(value: str):
  for fmt in ['%H:%M', '%H:%M:%S']:
    try:
      return datetime.strptime(value, fmt).time()
    except ValueError:
      continue
  raise ValueError(f'Formato orario non riconosciuto: {value}')


def _clean_caps(raw) -> list[str]:
  # Dedup preservando l'ordine di inserimento: due CAP uguali nello stesso
  # blocco non aggiungerebbero informazione e romperebbero il vincolo sotto.
  seen = []
  for cap in raw or []:
    cap = str(cap).strip()
    if cap and cap not in seen:
      seen.append(cap)
  return seen


@delivery_coverage_bp.route('', methods=['GET'])
@flask_session_authentication(COVERAGE_ROLES)
def get_delivery_coverage(_):
  return {'status': 'ok', 'entries': query_entries()}


@delivery_coverage_bp.route('', methods=['POST'])
@flask_session_authentication(COVERAGE_ROLES)
def create_delivery_coverage_entry(_):
  day_of_week = request.json['day_of_week']
  if day_of_week not in list(range(7)):
    raise ValueError('Invalid day_of_week value')

  transport = get_by_id(Transport, int(request.json['transport_id']))
  if not transport:
    return {'status': 'ko', 'message': 'Veicolo non trovato'}

  start_time = _parse_time(request.json['start_time'])
  end_time = _parse_time(request.json['end_time'])
  if end_time <= start_time:
    return {'status': 'ko', 'message': "L'orario di fine deve essere successivo a quello di inizio"}

  caps = _clean_caps(request.json.get('caps'))
  if not caps:
    return {'status': 'ko', 'message': 'Seleziona almeno un CAP'}

  entry = create(
    DeliveryCoverageEntry,
    {'day_of_week': day_of_week, 'transport_id': transport.id, 'start_time': start_time, 'end_time': end_time},
  )
  create_bulk(DeliveryCoverageCap, [{'entry_id': entry.id, 'cap': cap} for cap in caps])

  return {'status': 'ok', 'entry': get_entry_dict(entry.id)}


@delivery_coverage_bp.route('<id>', methods=['PUT'])
@flask_session_authentication(COVERAGE_ROLES)
def update_delivery_coverage_entry(_, id):
  entry: DeliveryCoverageEntry = get_by_id(DeliveryCoverageEntry, int(id))
  if not entry:
    return {'status': 'ko', 'message': 'Blocco non trovato'}

  data = {}
  if 'day_of_week' in request.json:
    day_of_week = request.json['day_of_week']
    if day_of_week not in list(range(7)):
      raise ValueError('Invalid day_of_week value')
    data['day_of_week'] = day_of_week

  if 'transport_id' in request.json:
    transport = get_by_id(Transport, int(request.json['transport_id']))
    if not transport:
      return {'status': 'ko', 'message': 'Veicolo non trovato'}
    data['transport_id'] = transport.id

  if 'start_time' in request.json:
    data['start_time'] = _parse_time(request.json['start_time'])
  if 'end_time' in request.json:
    data['end_time'] = _parse_time(request.json['end_time'])

  start_time = data.get('start_time', entry.start_time)
  end_time = data.get('end_time', entry.end_time)
  if end_time <= start_time:
    return {'status': 'ko', 'message': "L'orario di fine deve essere successivo a quello di inizio"}

  if data:
    update(entry, data)

  if 'caps' in request.json:
    caps = _clean_caps(request.json['caps'])
    if not caps:
      return {'status': 'ko', 'message': 'Seleziona almeno un CAP'}
    delete_bulk(query_caps(entry.id))
    create_bulk(DeliveryCoverageCap, [{'entry_id': entry.id, 'cap': cap} for cap in caps])

  return {'status': 'ok', 'entry': get_entry_dict(int(id))}


@delivery_coverage_bp.route('<id>', methods=['DELETE'])
@flask_session_authentication(COVERAGE_ROLES)
def delete_delivery_coverage_entry(_, id):
  entry: DeliveryCoverageEntry = get_by_id(DeliveryCoverageEntry, int(id))
  if not entry:
    return {'status': 'ko', 'message': 'Blocco non trovato'}

  delete(entry)
  return {'status': 'ok', 'message': 'Operazione completata'}


def format_entry(entry: DeliveryCoverageEntry) -> dict:
  # Chiamata solo con `entry` ancora legato a una sessione e caps già
  # caricati (query_entries, get_entry_dict): fuori da lì il lazy load su
  # istanza scollegata solleverebbe. Nome e targa del veicolo si risolvono
  # lato frontend dal transport_id (store dei veicoli già caricato), niente
  # join qui.
  return {
    **entry.to_dict(),
    'caps': sorted(cap.cap for cap in entry.caps),
  }


def get_entry_dict(entry_id: int) -> dict:
  with Session() as session:
    entry = (
      session.query(DeliveryCoverageEntry)
      .options(joinedload(DeliveryCoverageEntry.caps))
      .filter(DeliveryCoverageEntry.id == entry_id)
      .one()
    )
    return format_entry(entry)


def query_entries() -> list[dict]:
  with Session() as session:
    entries = (
      session.query(DeliveryCoverageEntry)
      .options(joinedload(DeliveryCoverageEntry.caps))
      .order_by(asc(DeliveryCoverageEntry.day_of_week), asc(DeliveryCoverageEntry.start_time))
      .all()
    )
    return [format_entry(entry) for entry in entries]


def query_caps(entry_id: int) -> list[DeliveryCoverageCap]:
  with Session() as session:
    return session.query(DeliveryCoverageCap).filter(DeliveryCoverageCap.entry_id == entry_id).all()

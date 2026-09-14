from datetime import date, datetime, timedelta

from dateutil.relativedelta import relativedelta
from sqlalchemy import asc
from sqlalchemy.orm import joinedload
from flask import Blueprint, request

from database_api import Session
from ..database.enum import UserRole
from . import flask_session_authentication
from database_api.operations import create, create_bulk, delete, delete_bulk, update, get_by_id
from ..database.schema import Order, Transport, DeliveryCoverageEntry, DeliveryCoverageCap


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


def _as_date(value):
  if isinstance(value, str):
    try:
      return datetime.strptime(value[:10], '%Y-%m-%d').date()
    except ValueError:
      return None
  return value


def available_slots(cap: str, dpc) -> list[dict]:
  """Fasce orarie distinte coperte dal CAP nel giorno della settimana di dpc,
  per il calendario di selezione data+fascia lato cliente: più blocchi
  (veicoli) sulla stessa fascia contano come un'unica fascia selezionabile.
  """
  dpc = _as_date(dpc)
  if not cap or not dpc:
    return []
  entries = [entry for entry in query_entries_for_cap(cap) if entry.day_of_week == dpc.weekday()]
  slots = sorted({(entry.start_time, entry.end_time) for entry in entries})
  return [{'start': start.strftime('%H:%M'), 'end': end.strftime('%H:%M')} for start, end in slots]


def available_slots_by_date(cap: str) -> dict:
  # Sostituisce il vecchio check_geographic_zone in /check-constraints: la
  # data prevista dal cliente è selezionabile se il suo CAP è coperto da
  # almeno un blocco di copertura corrieri in quel giorno della settimana.
  # Nessun conteggio ordini/giorno qui: la copertura non ha (ancora) un tetto
  # massimo, a differenza del vecchio Constraint.max_orders.
  covered_days = {entry.day_of_week for entry in query_entries_for_cap(cap)}
  start = datetime.today().date()
  end = start + relativedelta(months=2)
  result = {}
  while start <= end:
    if start.weekday() in covered_days:
      result[start.strftime('%Y-%m-%d')] = available_slots(cap, start)
    start += timedelta(days=1)
  return result


def check_delivery_coverage() -> list[str]:
  return list(available_slots_by_date(request.json['cap']).keys())


def check_delivery_coverage_slots() -> dict:
  return available_slots_by_date(request.json['cap'])


def resolve_delivery_slot(
  cap: str, dpc, requested_start=None, requested_end=None, exclude_order_id: int = None
) -> tuple:
  """CAP + data prevista dal cliente -> fascia oraria (start_time, end_time)
  da assegnare all'ordine, in base alla copertura corrieri. Se il cliente ha
  scelto esplicitamente una fascia dal calendario (requested_start/end), la
  usa se corrisponde a un blocco di copertura reale. Altrimenti (client non
  aggiornato, scelta non valida, o ordine creato da un operatore/admin che
  non passa dal calendario) ricade sull'automatismo storico: se più blocchi
  coprono lo stesso CAP nello stesso giorno (veicoli/fasce diversi), sceglie
  quello con meno ordini già presenti su quel CAP+giorno+fascia, per
  bilanciare il carico tra i veicoli. Ritorna (None, None) se il CAP non è
  coperto quel giorno: niente fascia, come oggi.
  """
  if not cap or not dpc:
    return None, None

  dpc = _as_date(dpc)
  if dpc is None:
    return None, None

  entries = [entry for entry in query_entries_for_cap(cap) if entry.day_of_week == dpc.weekday()]
  if not entries:
    return None, None

  if requested_start and requested_end:
    start_time = _parse_time(requested_start) if isinstance(requested_start, str) else requested_start
    end_time = _parse_time(requested_end) if isinstance(requested_end, str) else requested_end
    if any(entry.start_time == start_time and entry.end_time == end_time for entry in entries):
      return start_time, end_time

  if len(entries) == 1:
    return entries[0].start_time, entries[0].end_time

  slots = [(entry.start_time, entry.end_time) for entry in entries]
  counts = count_orders_by_slot(cap, dpc, slots, exclude_order_id)
  entries.sort(key=lambda entry: (counts[(entry.start_time, entry.end_time)], entry.start_time, entry.id))
  chosen = entries[0]
  return chosen.start_time, chosen.end_time


def query_entries_for_cap(cap: str) -> list[DeliveryCoverageEntry]:
  with Session() as session:
    return (
      session.query(DeliveryCoverageEntry)
      .join(DeliveryCoverageCap, DeliveryCoverageCap.entry_id == DeliveryCoverageEntry.id)
      .filter(DeliveryCoverageCap.cap == cap)
      .all()
    )


def count_orders_by_slot(cap: str, dpc: date, slots: list[tuple], exclude_order_id: int = None) -> dict:
  with Session() as session:
    query = session.query(Order).filter(Order.cap == cap, Order.dpc == dpc)
    if exclude_order_id:
      query = query.filter(Order.id != exclude_order_id)
    orders = query.all()

  counts = {slot: 0 for slot in slots}
  for order in orders:
    key = (order.delivery_slot_start, order.delivery_slot_end)
    if key in counts:
      counts[key] += 1
  return counts

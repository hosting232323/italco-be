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


def _has_overlapping_entry(transport_id: int, day_of_week: int, start_time, end_time, exclude_id: int = None) -> bool:
  # Stesso veicolo non può coprire due fasce sovrapposte nello stesso giorno;
  # veicoli diversi possono invece coprire la stessa fascia (vedi
  # test_multiple_entries_same_day_allowed / query_entries_for_cap).
  with Session() as session:
    query = session.query(DeliveryCoverageEntry).filter(
      DeliveryCoverageEntry.transport_id == transport_id,
      DeliveryCoverageEntry.day_of_week == day_of_week,
      DeliveryCoverageEntry.start_time < end_time,
      DeliveryCoverageEntry.end_time > start_time,
    )
    if exclude_id is not None:
      query = query.filter(DeliveryCoverageEntry.id != exclude_id)
    return session.query(query.exists()).scalar()


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

  if _has_overlapping_entry(transport.id, day_of_week, start_time, end_time):
    return {'status': 'ko', 'message': 'Il veicolo ha già una fascia sovrapposta in quel giorno'}

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

  transport_id = data.get('transport_id', entry.transport_id)
  day_of_week = data.get('day_of_week', entry.day_of_week)
  if _has_overlapping_entry(transport_id, day_of_week, start_time, end_time, exclude_id=entry.id):
    return {'status': 'ko', 'message': 'Il veicolo ha già una fascia sovrapposta in quel giorno'}

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


def available_slots(
  cap: str,
  dpc,
  required_duration: int = 0,
  exclude_order_id: int = None,
  new_cap: str = None,
  new_address: str = None,
) -> list[dict]:
  """Fasce orarie coperte dal CAP nel giorno della settimana di dpc con capienza residua

  sufficiente per la durata richiesta dei servizi dell'ordine. Include il travel overhead
  (tempo percorso aggiuntivo) nel calcolo dei minuti occupati.

  Una riga per blocco di copertura, non deduplicata per orario: blocchi di veicoli diversi
  che coprono la stessa fascia restano entrambi in lista (resolve_delivery_slot sceglie poi
  il veicolo migliore alla creazione dell'ordine), distinti dai CAP che coprono così il
  cliente non si trova davanti due opzioni identiche senza sapere perché sono separate.
  """
  dpc = _as_date(dpc)
  if not cap or not dpc:
    return []
  entries = [entry for entry in query_entries_for_cap(cap) if entry.day_of_week == dpc.weekday()]
  if not entries:
    return []

  from .service.duration import get_entry_capacity_minutes, entry_occupied_duration

  available = []
  with Session() as session:
    for entry in entries:
      capacity = get_entry_capacity_minutes(entry)
      occupied = entry_occupied_duration(
        entry,
        dpc,
        exclude_order_id=exclude_order_id,
        session=session,
        new_cap=new_cap,
        new_address=new_address,
      )
      if capacity == 0 or (occupied + required_duration <= capacity):
        available.append(entry)

  available.sort(key=lambda entry: (entry.start_time, entry.end_time, sorted(c.cap for c in entry.caps)))
  return [
    {
      'start': entry.start_time.strftime('%H:%M'),
      'end': entry.end_time.strftime('%H:%M'),
      'caps': sorted(c.cap for c in entry.caps),
    }
    for entry in available
  ]


def available_slots_by_date(
  cap: str,
  required_duration: int = 0,
  exclude_order_id: int = None,
  new_cap: str = None,
  new_address: str = None,
) -> dict:
  # Sostituisce il vecchio check_geographic_zone in /check-constraints: la
  # data prevista dal cliente è selezionabile se il suo CAP è coperto da
  # almeno un blocco di copertura corrieri con capienza residua per i servizi
  # dell'ordine in quel giorno della settimana.
  covered_days = {entry.day_of_week for entry in query_entries_for_cap(cap)}
  start = datetime.today().date()
  end = start + relativedelta(months=2)
  result = {}
  while start <= end:
    if start.weekday() in covered_days:
      slots = available_slots(
        cap,
        start,
        required_duration=required_duration,
        exclude_order_id=exclude_order_id,
        new_cap=new_cap,
        new_address=new_address,
      )
      if slots:
        result[start.strftime('%Y-%m-%d')] = slots
    start += timedelta(days=1)
  return result


def check_delivery_coverage(*args, **kwargs) -> list[str]:
  payload = request.json or {}
  from .service.duration import calculate_payload_service_duration

  user = kwargs.get('user') or (args[0] if args else None)
  required_duration = calculate_payload_service_duration(payload, user=user)
  exclude_order_id = payload.get('order_id')
  new_cap = payload.get('cap')
  return list(
    available_slots_by_date(
      new_cap,
      required_duration=required_duration,
      exclude_order_id=exclude_order_id,
      new_cap=new_cap,
      new_address=payload.get('address'),
    ).keys()
  )


def check_delivery_coverage_slots(*args, **kwargs) -> dict:
  payload = request.json or {}
  from .service.duration import calculate_payload_service_duration

  user = kwargs.get('user') or (args[0] if args else None)
  required_duration = calculate_payload_service_duration(payload, user=user)
  exclude_order_id = payload.get('order_id')
  new_cap = payload.get('cap')
  return available_slots_by_date(
    new_cap,
    required_duration=required_duration,
    exclude_order_id=exclude_order_id,
    new_cap=new_cap,
    new_address=payload.get('address'),
  )


def resolve_delivery_slot(
  cap: str,
  dpc,
  requested_start=None,
  requested_end=None,
  exclude_order_id: int = None,
  required_duration: int = 0,
  products: dict = None,
  user_id: int = None,
  address: str = None,
) -> tuple:
  """CAP + data prevista dal cliente -> fascia oraria (start_time, end_time)

  da assegnare all'ordine, in base alla copertura corrieri e al tempo dei servizi
  più il tempo di percorso aggiuntivo introdotto dall'ordine.
  """
  if not cap or not dpc:
    return None, None

  dpc = _as_date(dpc)
  if dpc is None:
    return None, None

  entries = [entry for entry in query_entries_for_cap(cap) if entry.day_of_week == dpc.weekday()]
  if not entries:
    return None, None

  from .service.duration import (
    calculate_order_service_duration,
    calculate_payload_service_duration,
    get_entry_capacity_minutes,
    query_slot_orders,
  )

  if required_duration == 0 and products:
    required_duration = calculate_payload_service_duration({'products': products, 'user_id': user_id})

  if requested_start and requested_end:
    start_time = _parse_time(requested_start) if isinstance(requested_start, str) else requested_start
    end_time = _parse_time(requested_end) if isinstance(requested_end, str) else requested_end
    if any(entry.start_time == start_time and entry.end_time == end_time for entry in entries):
      return start_time, end_time

  if len(entries) == 1:
    return entries[0].start_time, entries[0].end_time

  with Session() as session:
    entry_stats = []
    for entry in entries:
      cap_minutes = get_entry_capacity_minutes(entry)
      orders = query_slot_orders(entry, dpc, exclude_order_id=exclude_order_id, session=session)
      occupied = sum(calculate_order_service_duration(o) for o in orders)
      # Includi travel overhead nella valutazione della fascia migliore
      if address and cap:
        from .service.travel import calculate_travel_overhead_minutes

        travel_overhead = calculate_travel_overhead_minutes(orders, cap, new_address=address)
      else:
        travel_overhead = 0
      total_occupied = occupied + travel_overhead
      order_count = len(orders)
      has_capacity = cap_minutes == 0 or (total_occupied + required_duration <= cap_minutes)
      entry_stats.append((has_capacity, total_occupied, order_count, entry))

  # Priorità ai blocchi con capienza residua, poi minor tempo occupato (incluso travel),
  # minor numero ordini, poi start_time
  entry_stats.sort(key=lambda s: (not s[0], s[1], s[2], s[3].start_time, s[3].id))
  chosen = entry_stats[0][3]
  return chosen.start_time, chosen.end_time


def query_entries_for_cap(cap: str) -> list[DeliveryCoverageEntry]:
  with Session() as session:
    return (
      session.query(DeliveryCoverageEntry)
      .options(joinedload(DeliveryCoverageEntry.caps))
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

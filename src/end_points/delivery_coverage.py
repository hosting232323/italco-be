from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta
from sqlalchemy import and_, asc, or_
from sqlalchemy.orm import joinedload
from flask import Blueprint, request

from database_api import Session
from ..database.enum import UserRole
from . import flask_session_authentication
from database_api.operations import create, create_bulk, delete, delete_bulk, update, get_by_id
from ..database.schema import (
  DeliveryCoverageCap,
  DeliveryCoverageEntry,
  Order,
  Product,
  Schedule,
  ScheduleItem,
  ScheduleItemCollectionPoint,
  ScheduleItemOrder,
  Transport,
)
from ..utils.geo import parse_coordinates, point_in_polygon
from ..utils.caps import get_lat_lon_by_address, get_lat_lon_by_cap, remember_address_coordinates


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


def _clean_polygon(raw) -> list | None:
  # Un blocco disegnato sulla mappa in alternativa al CAP: lista di vertici
  # [lat, lon]. Sotto i 3 punti non è un poligono, quindi non lo salviamo
  # (torna None, come se il campo non fosse stato passato).
  if not raw:
    return None
  points = []
  for point in raw:
    lat, lon = point
    points.append([float(lat), float(lon)])
  return points if len(points) >= 3 else None


@delivery_coverage_bp.route('', methods=['GET'])
@flask_session_authentication(COVERAGE_ROLES, automatic_planning_required=True)
def get_delivery_coverage(_):
  return {'status': 'ok', 'entries': query_entries()}


@delivery_coverage_bp.route('', methods=['POST'])
@flask_session_authentication(COVERAGE_ROLES, automatic_planning_required=True)
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
  polygon = _clean_polygon(request.json.get('polygon'))
  if not caps and not polygon:
    return {'status': 'ko', 'message': 'Seleziona almeno un CAP o disegna una zona sulla mappa'}

  entry = create(
    DeliveryCoverageEntry,
    {
      'day_of_week': day_of_week,
      'transport_id': transport.id,
      'start_time': start_time,
      'end_time': end_time,
      'polygon': polygon,
      'accepts_preloads': bool(request.json.get('accepts_preloads')),
    },
  )
  if caps:
    create_bulk(DeliveryCoverageCap, [{'entry_id': entry.id, 'cap': cap} for cap in caps])

  return {'status': 'ok', 'entry': get_entry_dict(entry.id)}


@delivery_coverage_bp.route('<id>', methods=['PUT'])
@flask_session_authentication(COVERAGE_ROLES, automatic_planning_required=True)
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

  # Stato finale (caps ed entry.polygon letti PRIMA di qualunque update sotto,
  # per validare senza aver già scritto uno stato parziale non valido).
  polygon_provided = 'polygon' in request.json
  new_polygon = _clean_polygon(request.json['polygon']) if polygon_provided else None
  caps_provided = 'caps' in request.json
  new_caps = _clean_caps(request.json['caps']) if caps_provided else None

  final_polygon = new_polygon if polygon_provided else entry.polygon
  # entry arriva da get_by_id, scollegato dalla sessione: niente lazy load su
  # entry.caps (relationship), va riletto esplicitamente con query_caps.
  final_has_caps = bool(new_caps) if caps_provided else bool(query_caps(entry.id))
  if not final_has_caps and not final_polygon:
    return {'status': 'ko', 'message': 'Seleziona almeno un CAP o disegna una zona sulla mappa'}

  if polygon_provided:
    data['polygon'] = new_polygon
  if 'accepts_preloads' in request.json:
    data['accepts_preloads'] = bool(request.json['accepts_preloads'])
  if data:
    update(entry, data)

  if caps_provided:
    delete_bulk(query_caps(entry.id))
    if new_caps:
      create_bulk(DeliveryCoverageCap, [{'entry_id': entry.id, 'cap': cap} for cap in new_caps])

  return {'status': 'ok', 'entry': get_entry_dict(int(id))}


@delivery_coverage_bp.route('<id>', methods=['DELETE'])
@flask_session_authentication(COVERAGE_ROLES, automatic_planning_required=True)
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


def _adjacent_coverage_entries(entry: DeliveryCoverageEntry, session) -> list[DeliveryCoverageEntry]:
  """Fasce dello stesso veicolo (stesso transport_id) e giorno della settimana,

  immediatamente prima e/o dopo `entry` in ordine cronologico. Non filtrate per CAP:
  il veicolo passa comunque di lì subito prima/dopo, indipendentemente dalla zona che
  quella fascia copre ufficialmente. Un eventuale buco tra le due fasce (es. 11:30-12:00)
  non esclude l'adiacenza: conta l'ordine cronologico, non la contiguità esatta.
  """
  siblings = (
    session.query(DeliveryCoverageEntry)
    .filter(
      DeliveryCoverageEntry.transport_id == entry.transport_id,
      DeliveryCoverageEntry.day_of_week == entry.day_of_week,
      DeliveryCoverageEntry.id != entry.id,
    )
    .all()
  )
  before = [s for s in siblings if s.end_time <= entry.start_time]
  after = [s for s in siblings if s.start_time >= entry.end_time]
  adjacent = []
  if before:
    adjacent.append(max(before, key=lambda s: s.end_time))
  if after:
    adjacent.append(min(after, key=lambda s: s.start_time))
  return adjacent


def _passes_same_pickup_points(
  entry: DeliveryCoverageEntry,
  dpc,
  new_products: dict,
  session,
  exclude_order_id: int = None,
  address: tuple | None = None,
) -> bool:
  """Se il veicolo di `entry` passa già dai punti di ritiro precaricabili dell'ordine in `dpc` o il giorno prima.

  Vale solo per le aree che accettano precarichi (accepts_preloads) e solo per
  i punti di ritiro che l'ordine può precaricare: punto col precarico attivo e
  indirizzo di consegna nelle sue aree di precarico (o, se il punto non ne ha,
  nell'area di copertura), come in order_is_preloaded. Per questi punti la
  fascia si offre solo se il borderò dello stesso veicolo ci passa quel giorno
  (il prodotto si ritira lì) o il giorno prima (precarico: si aggancia al
  passaggio della vigilia, vedi schedule/preload.py); un punto senza passaggio
  scarta la fascia. Una vigilia nel passato non conta.
  Gli altri punti (senza precarico, o con un destinatario fuori dalle aree di
  precarico del punto) seguono le regole normali della pianificazione: nessun
  vincolo, il ritiro si aggiunge al borderò del giorno della consegna.
  `address` (cap, lat, lon) è l'indirizzo di consegna.
  Il passaggio si legge dal borderò reale, non dal veicolo salvato sull'ordine.
  Un ordine senza punti di ritiro precaricabili non ha nulla da incrociare.
  """
  if not entry.accepts_preloads:
    return True
  from .schedule.preload import preloaded_collection_point_ids
  from .service.duration import payload_pickup_collection_point_ids

  collection_point_ids = set(payload_pickup_collection_point_ids(new_products or {}))
  if not collection_point_ids:
    return True
  preloaded_ids = preloaded_collection_point_ids(collection_point_ids, session, address=address, zone_accepts=True)
  if not preloaded_ids:
    return True
  dpc = _as_date(dpc)
  if dpc is None:
    return False
  eve = dpc - timedelta(days=1)
  days = [dpc, eve] if eve >= date.today() else [dpc]
  return all(
    schedules_pass_pickup_points(
      {cp_id: days},
      session,
      transport_id=entry.transport_id,
      exclude_order_id=exclude_order_id,
    )
    for cp_id in preloaded_ids
  )


def schedules_pass_pickup_points(
  days_by_point: dict, session, transport_id: int = None, exclude_order_id: int = None
) -> bool:
  """Se un borderò (del veicolo `transport_id`, se dato) passa da almeno uno dei punti di ritiro nei giorni indicati.

  `days_by_point` è {collection_point_id: [date, ...]}. Conta il borderò reale
  (la data dello Schedule), non la dpc né il veicolo salvati sull'ordine: un
  ordine messo a mano nel borderò dall'operatore non ha `delivery_transport_id`
  e può stare in un borderò con una data diversa dalla sua dpc. Un borderò passa
  da un punto se ha la tappa di ritiro di quel punto, chiunque l'abbia messa
  (operatore, altri ordini o l'ordine in modifica: è un passaggio vero), o un
  ordine con un prodotto da ritirare lì quel giorno. Il prodotto di un ordine
  precaricato non conta: si ritira la vigilia, non nel borderò della consegna.
  `exclude_order_id` è l'ordine in modifica: i suoi prodotti non contano come
  passaggio. Ordini annullati o non pianificati non contano.
  """
  if not days_by_point:
    return False
  pickup_stop = (
    session.query(Schedule.id)
    .join(ScheduleItem, ScheduleItem.schedule_id == Schedule.id)
    .join(ScheduleItemCollectionPoint, ScheduleItemCollectionPoint.schedule_item_id == ScheduleItem.id)
    .filter(
      or_(
        *[
          and_(Schedule.date.in_(days), ScheduleItemCollectionPoint.collection_point_id == cp_id)
          for cp_id, days in days_by_point.items()
        ]
      )
    )
  )
  if transport_id:
    pickup_stop = pickup_stop.filter(Schedule.transport_id == transport_id)
  # Prima le tappe di ritiro: una query sola, e la tappa della vigilia di un
  # ordine precaricato risponde subito senza ripercorrere i giorni prima.
  if pickup_stop.first() is not None:
    return True

  from .schedule.preload import preloaded_pickup_ids_for_order

  order_stop = (
    session.query(ScheduleItemOrder.order_id, Product.collection_point_id)
    .select_from(Schedule)
    .join(ScheduleItem, ScheduleItem.schedule_id == Schedule.id)
    .join(ScheduleItemOrder, ScheduleItemOrder.schedule_item_id == ScheduleItem.id)
    .join(Product, Product.order_id == ScheduleItemOrder.order_id)
    .filter(
      or_(
        *[and_(Schedule.date.in_(days), Product.collection_point_id == cp_id) for cp_id, days in days_by_point.items()]
      )
    )
  )
  if transport_id:
    order_stop = order_stop.filter(Schedule.transport_id == transport_id)
  if exclude_order_id:
    order_stop = order_stop.filter(ScheduleItemOrder.order_id != exclude_order_id)
  for order_id, cp_id in order_stop.distinct():
    order = session.get(Order, order_id)
    if not order.preloaded or cp_id not in preloaded_pickup_ids_for_order(order, session):
      return True
  return False


def _eve_can_take_preloads(
  entry: DeliveryCoverageEntry,
  dpc,
  new_products: dict,
  session,
  exclude_order_id: int = None,
  address: tuple | None = None,
) -> bool:
  """Se la vigilia del veicolo ha tempo per i ritiri precaricati del nuovo ordine.

  I ritiri precaricati si fanno in testa alla giornata prima (prima fascia del
  veicolo): pesano su quella fascia, non su quella della consegna. Senza
  precarichi, o con una fascia senza capienza dichiarata, nessun vincolo.
  """
  if not entry.accepts_preloads:
    return True
  from .schedule.preload import preload_ready_ids, preloaded_collection_point_ids
  from .service.duration import (
    PICKUP_POINT_MINUTES_PER_PRODUCT,
    entry_occupied_duration,
    get_entry_capacity_minutes,
    payload_pickup_collection_point_ids,
  )

  pickup_ids = payload_pickup_collection_point_ids(new_products or {})
  dpc = _as_date(dpc)
  if dpc is None:
    return True
  preloaded_ids = preload_ready_ids(
    dpc,
    entry.transport_id,
    preloaded_collection_point_ids(set(pickup_ids), session, address=address, zone_accepts=True),
    session,
    exclude_order_id=exclude_order_id,
  )
  if not preloaded_ids:
    return True

  eve = dpc - timedelta(days=1)
  first = (
    session.query(DeliveryCoverageEntry)
    .filter(
      DeliveryCoverageEntry.transport_id == entry.transport_id, DeliveryCoverageEntry.day_of_week == eve.weekday()
    )
    .order_by(DeliveryCoverageEntry.start_time)
    .first()
  )
  capacity = get_entry_capacity_minutes(first)
  if not capacity:
    return True
  occupied = entry_occupied_duration(first, eve, exclude_order_id=exclude_order_id, session=session)
  new_minutes = PICKUP_POINT_MINUTES_PER_PRODUCT * len([cp_id for cp_id in pickup_ids if cp_id in preloaded_ids])
  return occupied + new_minutes <= capacity


def _entry_with_residual_capacity(
  entry: DeliveryCoverageEntry,
  dpc,
  required_duration: int,
  session,
  exclude_order_id: int = None,
  new_cap: str = None,
  new_address: str = None,
  new_products: dict = None,
) -> DeliveryCoverageEntry | None:
  """`entry` se ha capienza residua per `required_duration`, altrimenti la fascia

  adiacente dello stesso veicolo (stesso giorno, vedi _adjacent_coverage_entries) che
  ce l'ha, altrimenti None se nemmeno quella ha spazio.
  """
  from .service.duration import get_entry_capacity_minutes, entry_occupied_duration

  def _has_capacity(candidate: DeliveryCoverageEntry) -> bool:
    capacity = get_entry_capacity_minutes(candidate)
    occupied = entry_occupied_duration(
      candidate,
      dpc,
      exclude_order_id=exclude_order_id,
      session=session,
      new_cap=new_cap,
      new_address=new_address,
      new_products=new_products,
    )
    return capacity == 0 or (occupied + required_duration <= capacity)

  if _has_capacity(entry):
    return entry

  for neighbor in _adjacent_coverage_entries(entry, session):
    if _has_capacity(neighbor):
      return neighbor

  return None


def _first_with_residual_capacity(
  entries: list[DeliveryCoverageEntry],
  dpc,
  required_duration: int,
  exclude_order_id: int = None,
  new_cap: str = None,
  new_address: str = None,
  new_products: dict = None,
) -> DeliveryCoverageEntry | None:
  """Il primo blocco di `entries` (già in ordine di priorità) che, direttamente o con la
  fascia adiacente dello stesso veicolo, ha capienza per `required_duration`."""
  with Session() as session:
    for entry in entries:
      effective = _entry_with_residual_capacity(
        entry,
        dpc,
        required_duration,
        session,
        exclude_order_id=exclude_order_id,
        new_cap=new_cap,
        new_address=new_address,
        new_products=new_products,
      )
      if effective is not None:
        return effective
  return None


def _slot_still_open(entry: DeliveryCoverageEntry, dpc) -> bool:
  """Se la fascia di `entry` in `dpc` non e' gia' finita: oggi non si offrono fasce passate.

  L'ora e' quella italiana, non quella del server (in Docker spesso UTC).
  """
  now = datetime.now(ZoneInfo('Europe/Rome'))
  return dpc != now.date() or entry.end_time > now.time()


def _note_blocked(blocked_slots: dict, entry: DeliveryCoverageEntry, reason: str) -> None:
  if blocked_slots is not None:
    blocked_slots.setdefault((entry.start_time, entry.end_time), set()).add(reason)


def available_slots(
  cap: str,
  dpc,
  required_duration: int = 0,
  exclude_order_id: int = None,
  new_cap: str = None,
  new_address: str = None,
  new_products: dict = None,
  entries: list[DeliveryCoverageEntry] = None,
  blocked_slots: dict = None,
) -> list[dict]:
  """Fasce orarie coperte dal CAP nel giorno della settimana di dpc con capienza residua

  sufficiente per la durata richiesta dei servizi dell'ordine. Include il travel overhead
  (tempo percorso aggiuntivo) e i minuti dei punti di ritiro (new_products) nel calcolo
  dei minuti occupati.

  Una riga per fascia oraria: blocchi di veicoli diversi con la stessa fascia (start/end
  identici) compaiono una volta sola, con l'unione dei CAP, e la scelta del veicolo è di
  resolve_delivery_slot alla creazione dell'ordine (si riempie prima la giornata di un
  veicolo, poi si passa al successivo).

  Una fascia è in lista se almeno uno dei suoi blocchi ha capienza residua o, se satura,
  se la fascia adiacente dello stesso veicolo (stesso giorno) ne ha: l'ordine potrà finire
  lì (vedi _entry_with_residual_capacity e resolve_delivery_slot, che applica la stessa
  logica alla creazione dell'ordine).

  `entries` sono i blocchi che coprono il CAP (query_entries_for_cap): chi chiama
  per molti giorni di fila li risolve una volta sola invece di ripetere, a ogni
  giorno, query e geocoding dell'indirizzo.

  `blocked_slots`, se passato, raccoglie per ogni fascia (start, end) senza
  nessun blocco disponibile i motivi per cui e' stata scartata: serve a spiegare
  perche' di un giorno coperto si possono scegliere solo certe fasce.
  """
  dpc = _as_date(dpc)
  if not cap or not dpc:
    return []
  if entries is None:
    entries = query_entries_for_cap(cap, address=new_address)
  entries = [entry for entry in entries if entry.day_of_week == dpc.weekday() and _slot_still_open(entry, dpc)]
  if not entries:
    return []

  from .schedule.preload import delivery_address

  address = delivery_address(new_cap or cap, new_address)
  available = {}
  with Session() as session:
    for entry in entries:
      if not _passes_same_pickup_points(
        entry, dpc, new_products, session, exclude_order_id=exclude_order_id, address=address
      ):
        _note_blocked(
          blocked_slots, entry, "Il veicolo non passa dai punti di ritiro dell'ordine quel giorno o il giorno prima"
        )
        continue
      if not _eve_can_take_preloads(
        entry, dpc, new_products, session, exclude_order_id=exclude_order_id, address=address
      ):
        _note_blocked(blocked_slots, entry, 'Il giorno prima il corriere non ha tempo per i ritiri precaricati')
        continue
      effective = _entry_with_residual_capacity(
        entry,
        dpc,
        required_duration,
        session,
        exclude_order_id=exclude_order_id,
        new_cap=new_cap,
        new_address=new_address,
        new_products=new_products,
      )
      if effective is not None:
        available.setdefault((entry.start_time, entry.end_time), []).append(entry)
      else:
        _note_blocked(blocked_slots, entry, "Capienza esaurita per i servizi dell'ordine")

  if blocked_slots is not None:
    for key in available:
      blocked_slots.pop(key, None)

  return [
    {
      'start': start.strftime('%H:%M'),
      'end': end.strftime('%H:%M'),
      'caps': sorted({c.cap for entry in group for c in entry.caps}),
    }
    for (start, end), group in sorted(available.items())
  ]


def available_slots_by_date(
  cap: str,
  required_duration: int = 0,
  exclude_order_id: int = None,
  new_cap: str = None,
  new_address: str = None,
  new_products: dict = None,
  blocked_out: dict = None,
  slot_notes_out: dict = None,
) -> dict:
  # Sostituisce il vecchio check_geographic_zone in /check-constraints: la
  # data prevista dal cliente è selezionabile se il suo CAP è coperto da
  # almeno un blocco di copertura corrieri con capienza residua per i servizi
  # dell'ordine in quel giorno della settimana.
  entries = query_entries_for_cap(cap, address=new_address)
  covered_days = {entry.day_of_week for entry in entries}
  start = datetime.today().date()
  end = start + relativedelta(months=2)
  result = {}
  while start <= end:
    iso = start.strftime('%Y-%m-%d')
    if start.weekday() in covered_days:
      blocked_slots = {} if (blocked_out is not None or slot_notes_out is not None) else None
      slots = available_slots(
        cap,
        start,
        required_duration=required_duration,
        exclude_order_id=exclude_order_id,
        new_cap=new_cap,
        new_address=new_address,
        new_products=new_products,
        entries=entries,
        blocked_slots=blocked_slots,
      )
      if slots:
        result[iso] = slots
        if slot_notes_out is not None and blocked_slots:
          slot_notes_out[iso] = [
            {'start': s_start.strftime('%H:%M'), 'end': s_end.strftime('%H:%M'), 'reason': ' · '.join(sorted(reasons))}
            for (s_start, s_end), reasons in sorted(blocked_slots.items())
          ]
      elif blocked_out is not None:
        all_reasons = set().union(*blocked_slots.values()) if blocked_slots else set()
        blocked_out[iso] = ' · '.join(sorted(all_reasons)) or 'Nessuna fascia disponibile'
    elif blocked_out is not None and entries:
      blocked_out[iso] = f'Nessun corriere in copertura di {WEEKDAY_NAMES[start.weekday()]}'
    start += timedelta(days=1)
  return result


WEEKDAY_NAMES = ['lunedì', 'martedì', 'mercoledì', 'giovedì', 'venerdì', 'sabato', 'domenica']


def check_delivery_coverage(*args, **kwargs) -> list[str]:
  # Le date sono le chiavi delle fasce: un calcolo solo, non due.
  return list(check_delivery_coverage_slots(*args, **kwargs).keys())


def check_delivery_coverage_slots(*args, **kwargs) -> dict:
  payload = request.json or {}
  from .service.duration import calculate_payload_service_duration

  user = kwargs.get('user') or (args[0] if args else None)
  required_duration = calculate_payload_service_duration(payload, user=user)
  exclude_order_id = payload.get('order_id')
  # Il CAP e' una stringa a DB: un numero nel JSON darebbe un errore di tipo nella query.
  new_cap = str(payload['cap']) if payload.get('cap') is not None else None
  # Indirizzo scelto dal menu Google: zone, capienza e strada usano la sua
  # posizione esatta invece di geocodificarlo con Nominatim.
  remember_address_coordinates(
    payload.get('address'), *parse_coordinates(payload.get('address_lat'), payload.get('address_lon'))
  )
  extra = {key: kwargs[key] for key in ('blocked_out', 'slot_notes_out') if kwargs.get(key) is not None}
  return available_slots_by_date(
    new_cap,
    required_duration=required_duration,
    exclude_order_id=exclude_order_id,
    new_cap=new_cap,
    new_address=payload.get('address'),
    new_products=payload.get('products'),
    **extra,
  )


class SlotUnavailableError(Exception):
  """Il giorno e' coperto ma nessuna fascia ha piu' capienza per l'ordine."""


def resolve_delivery_entry(
  cap: str,
  dpc,
  requested_start=None,
  requested_end=None,
  exclude_order_id: int = None,
  required_duration: int = 0,
  products: dict = None,
  user_id: int = None,
  address: str = None,
) -> DeliveryCoverageEntry | None:
  """CAP + data prevista dal cliente -> blocco di copertura (veicolo + fascia)

  che prende l'ordine, in base alla copertura corrieri e al tempo dei servizi
  più il tempo di percorso aggiuntivo introdotto dall'ordine.

  None se la data non e' coperta da nessun blocco: l'ordine resta senza fascia e
  la dpc quella scelta a mano. Se e' coperta ma nessun blocco ha capienza
  solleva SlotUnavailableError: il cliente sceglie dalla lista delle
  disponibilita', se nel frattempo si e' riempita va rifiutato l'ordine, non
  caricato oltre la capienza. Il chiamante tiene il lock degli ordini, quindi
  tra questa scelta e la creazione dell'ordine nessun altro puo' inserirsi.
  """
  if not cap or not dpc:
    return None

  dpc = _as_date(dpc)
  if dpc is None:
    return None

  entries = [entry for entry in query_entries_for_cap(cap, address=address) if entry.day_of_week == dpc.weekday()]
  if not entries:
    return None
  entries = [entry for entry in entries if _slot_still_open(entry, dpc)]
  if not entries:
    raise SlotUnavailableError('Non ci sono più fasce disponibili per questa data: scegli un altro giorno')

  from .service.duration import calculate_payload_service_duration, entry_priority_key

  if required_duration == 0 and products:
    required_duration = calculate_payload_service_duration({'products': products, 'user_id': user_id})

  from .schedule.preload import delivery_address

  delivery = delivery_address(cap, address)
  with Session() as session:
    entries = [
      entry
      for entry in entries
      if _passes_same_pickup_points(entry, dpc, products, session, exclude_order_id=exclude_order_id, address=delivery)
      and _eve_can_take_preloads(entry, dpc, products, session, exclude_order_id=exclude_order_id, address=delivery)
    ]
  if not entries:
    raise SlotUnavailableError('Non ci sono più fasce disponibili per questa data: scegli un altro giorno')

  candidates = entries
  if requested_start and requested_end:
    start_time = _parse_time(requested_start) if isinstance(requested_start, str) else requested_start
    end_time = _parse_time(requested_end) if isinstance(requested_end, str) else requested_end
    requested_entries = [entry for entry in entries if entry.start_time == start_time and entry.end_time == end_time]
    # Una fascia che il CAP non offre non e' una scelta valida: si ricade sul
    # bilanciamento automatico invece di rifiutare.
    candidates = requested_entries or entries

  # Si riempie per veicolo: prima la sua giornata in ordine cronologico
  # (comprese le fasce adiacenti), poi il veicolo successivo.
  effective = _first_with_residual_capacity(
    sorted(candidates, key=entry_priority_key),
    dpc,
    required_duration,
    exclude_order_id=exclude_order_id,
    new_cap=cap,
    new_address=address,
    new_products=products,
  )
  if effective is None:
    raise SlotUnavailableError('Non ci sono più fasce disponibili per questa data: scegli un altro giorno')
  return effective


def resolve_delivery_slot(*args, **kwargs) -> tuple:
  """Come resolve_delivery_entry ma solo la fascia (start_time, end_time)."""
  entry = resolve_delivery_entry(*args, **kwargs)
  return (entry.start_time, entry.end_time) if entry else (None, None)


def query_entries_for_cap(cap: str, address: str = None) -> list[DeliveryCoverageEntry]:
  """Blocchi che coprono `cap` (match esatto) più i blocchi disegnati sulla mappa

  (senza CAP) il cui poligono contiene la posizione di `address`. Se l'indirizzo
  non si geocodifica nemmeno in modo approssimato si usa il centroide del CAP:
  senza una posizione una copertura fatta solo di zone su mappa lo darebbe
  sempre fuori zona.
  """
  with Session() as session:
    by_cap = (
      session.query(DeliveryCoverageEntry)
      .options(joinedload(DeliveryCoverageEntry.caps))
      .join(DeliveryCoverageCap, DeliveryCoverageCap.entry_id == DeliveryCoverageEntry.id)
      .filter(DeliveryCoverageCap.cap == cap)
      .all()
      if cap
      else []
    )

  if not address:
    return by_cap

  lat, lon = get_lat_lon_by_address(address)
  if lat is None and cap:
    lat, lon = get_lat_lon_by_cap(cap)
  if lat is None:
    return by_cap

  seen_ids = {entry.id for entry in by_cap}
  by_polygon = [entry for entry in query_entries_for_polygon_point(lat, lon) if entry.id not in seen_ids]
  return by_cap + by_polygon


def query_entries_for_polygon_point(lat: float, lon: float) -> list[DeliveryCoverageEntry]:
  """Blocchi disegnati sulla mappa il cui poligono contiene il punto (lat, lon)."""
  with Session() as session:
    entries = (
      session.query(DeliveryCoverageEntry)
      .options(joinedload(DeliveryCoverageEntry.caps))
      .filter(DeliveryCoverageEntry.polygon.isnot(None))
      .all()
    )
  return [entry for entry in entries if point_in_polygon((lat, lon), entry.polygon)]


def annotate_out_of_zone(orders: list[dict]) -> None:
  """Aggiunge `out_of_zone` a ogni ordine (dict) della lista.

  Fuori zona = nessun blocco di copertura copre il CAP dell'ordine ne' il suo
  poligono disegnato sulla mappa (con le coordinate salvate dell'indirizzo). Un
  ordine con veicolo assegnato e' per definizione coperto. Se non esiste nessun
  blocco la copertura non e' in uso e nessun ordine viene segnalato. Una sola
  lettura dei blocchi per l'intera lista, nessun geocoding.
  """
  if not orders:
    return
  with Session() as session:
    entries = session.query(DeliveryCoverageEntry).options(joinedload(DeliveryCoverageEntry.caps)).all()
  if not entries:
    for order in orders:
      order['out_of_zone'] = False
    return

  covered_caps = {str(cap.cap).strip() for entry in entries for cap in entry.caps}
  polygons = [entry.polygon for entry in entries if entry.polygon]
  for order in orders:
    if order.get('delivery_transport_id') or str(order.get('cap') or '').strip() in covered_caps:
      order['out_of_zone'] = False
      continue
    lat, lon = order.get('address_lat'), order.get('address_lon')
    in_polygon = lat is not None and lon is not None and any(point_in_polygon((lat, lon), p) for p in polygons)
    order['out_of_zone'] = not in_polygon


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

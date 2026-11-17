"""Collegamento dei punti di ritiro agli ordini e riordino del borderò via OSRM.

Ogni prodotto di un ordine può richiedere il ritiro presso un ``CollectionPoint``
(``Product.collection_point_id``). Un ordine può quindi dipendere da più punti di
ritiro, e più ordini possono condividere lo stesso punto di ritiro: in quel caso la
tappa ``CollectionPoint`` nel borderò va creata una sola volta e riusata.

Le tappe del borderò (``ScheduleItem``) si ordinano fascia oraria per fascia
oraria, in ordine cronologico: le consegne sono promesse al cliente in una fascia
e un ordine delle 9:40 non può finire dopo uno delle 11:30 solo perché è più
comodo come strada. Il giro di ogni fascia (vedi ``sequencing.py``) parte da dove
il veicolo si trova davvero: il deposito per la prima fascia, l'ultima tappa della
fascia prima per le successive, l'ultima tappa già fatta se il giro è iniziato.
Dentro la fascia l'unico vincolo è che un ritiro preceda le consegne che ne
dipendono: ordini della stessa zona finiscono uno dopo l'altro anche quando non
condividono un punto di ritiro.

Se OSRM non è raggiungibile si stima in linea d'aria; una tappa non
geocodificabile resta ai bordi della sua fascia (ritiri in testa, consegne in
coda) invece di far fallire la richiesta.
"""

import logging
from datetime import time, timedelta
from dataclasses import dataclass
from collections import defaultdict

from sqlalchemy.orm import Session as session_type

from database_api.operations import create, update, get_by_ids
from ..database.enum import ScheduleType
from ..database.schema import (
  CollectionPoint,
  DeliveryCoverageEntry,
  Order,
  Schedule,
  ScheduleItem,
  ScheduleItemCollectionPoint,
  ScheduleItemOrder,
  Transport,
)
from ..end_points.orders.queries import query_products
from ..end_points.schedule.preload import preloaded_pickup_ids_for_order
from ..end_points.schedule.queries import get_schedule_items, schedule_has_started
from .sequencing import duration_matrix, resolve_stop_coords, sequence_stops

logger = logging.getLogger(__name__)

Coord = tuple[float, float]


@dataclass
class StopContext:
  item: ScheduleItem
  kind: str  # 'order' o 'collection_point'
  coord: Coord | None
  entity_id: int  # order_id o collection_point_id


# ---------------------------------------------------------------------------
# Collegamento punti di ritiro <-> ordine
# ---------------------------------------------------------------------------


def required_collection_point_ids_for_order(order: Order, session: session_type) -> set[int]:
  """Punti di ritiro da visitare nel borderò di ``order``, dedotti dai suoi prodotti.

  Quelli precaricati non ci sono: si ritirano il giorno prima, nella tappa del
  borderò della vigilia (vedi ``link_preloaded_collection_points``).
  """
  ids = {p.collection_point_id for p in query_products(order, session=session) if p.collection_point_id}
  return ids - preloaded_pickup_ids_for_order(order, session)


def next_day_preloaded_ids(schedule: Schedule, session: session_type, exclude_order_id: int = None) -> set[int]:
  """Punti di ritiro che il borderò ``schedule`` visita per i precarichi del giorno dopo."""
  # Solo gli ordini pianificati: uno tolto dal borderò non ha piu' bisogno della tappa.
  planned_order_ids = session.query(ScheduleItemOrder.order_id)
  orders = (
    session.query(Order)
    .filter(
      Order.delivery_transport_id == schedule.transport_id,
      Order.dpc == schedule.date + timedelta(days=1),
      Order.preloaded.is_(True),
      Order.id.in_(planned_order_ids),
    )
    .all()
  )
  ids: set[int] = set()
  for order in orders:
    if order.id != exclude_order_id:
      ids |= preloaded_pickup_ids_for_order(order, session)
  return ids


def link_preloaded_collection_points(
  order: Order, transport_id: int, start_time_slot, end_time_slot, session, optimize: bool = True
):
  """Porta nel borderò della vigilia i ritiri precaricati di ``order``.

  Stesso veicolo, giorno prima della consegna. Se il borderò della vigilia non
  esiste lo crea (con le sole tappe di ritiro); le tappe già presenti si
  riusano, come per i ritiri normali.
  """
  preloaded_ids = preloaded_pickup_ids_for_order(order, session)
  if not preloaded_ids or not order.dpc:
    return []

  eve = order.dpc - timedelta(days=1)
  schedule = (
    session.query(Schedule).filter(Schedule.date == eve, Schedule.transport_id == transport_id).first()
  ) or create(Schedule, {'date': eve, 'transport_id': transport_id}, session=session)
  if schedule_has_started(schedule, session):
    return []
  first_item = (
    session.query(ScheduleItem).filter(ScheduleItem.schedule_id == schedule.id).order_by(ScheduleItem.index).first()
  )
  if first_item:
    start_time_slot, end_time_slot = first_item.start_time_slot, first_item.end_time_slot
  else:
    # Borderò della vigilia nuovo: la tappa non e' una consegna e non ha la
    # fascia di quella del giorno dopo. Prende la prima fascia che il veicolo
    # copre la vigilia (la consegna resta solo come ripiego).
    first_entry = (
      session.query(DeliveryCoverageEntry)
      .filter(DeliveryCoverageEntry.transport_id == transport_id, DeliveryCoverageEntry.day_of_week == eve.weekday())
      .order_by(DeliveryCoverageEntry.start_time)
      .first()
    )
    if first_entry:
      start_time_slot, end_time_slot = first_entry.start_time, first_entry.end_time
  created = link_missing_collection_points(
    order, schedule, start_time_slot, end_time_slot, session=session, collection_point_ids=preloaded_ids
  )
  if created and optimize:
    optimize_schedule_stops(schedule, session=session)
  return created


def link_missing_collection_points(
  order: Order,
  schedule: Schedule,
  start_time_slot,
  end_time_slot,
  session: session_type,
  collection_point_ids: set[int] = None,
) -> list[ScheduleItem]:
  """Crea nel borderò le tappe ``CollectionPoint`` richieste da ``order`` che non ci sono già.

  Un punto di ritiro già presente come tappa (perché richiesto da un altro
  ordine già pianificato nello stesso borderò) viene riusato, non duplicato.
  L'indice assegnato alle nuove tappe è provvisorio: va chiamato
  ``optimize_schedule_stops`` subito dopo per ricalcolare l'ordine di visita.

  ``start_time_slot``/``end_time_slot`` (in pratica la fascia del
  ``DeliveryCoverageEntry`` che ha innescato l'inserimento di ``order``) sono
  obbligatori: senza, la tappa nascerebbe con quei campi ``NULL`` e la lettura
  del borderò va in errore (``format_schedule_item`` ci chiama ``.strftime()``
  senza controllo, come fanno tutte le tappe create dal flusso manuale).

  ``collection_point_ids`` restringe i punti da collegare (i ritiri precaricati
  vanno nel borderò della vigilia); senza, sono quelli del borderò di consegna.

  Returns:
    Le nuove ``ScheduleItem`` create (lista vuota se non serviva nulla).
  """
  required_ids = (
    collection_point_ids
    if collection_point_ids is not None
    else required_collection_point_ids_for_order(order, session)
  )
  if not required_ids:
    return []

  existing_ids = {
    row.collection_point_id
    for row in session.query(ScheduleItemCollectionPoint.collection_point_id)
    .join(ScheduleItem, ScheduleItem.id == ScheduleItemCollectionPoint.schedule_item_id)
    .filter(ScheduleItem.schedule_id == schedule.id)
    .all()
  }

  missing_ids = required_ids - existing_ids
  if not missing_ids:
    return []

  next_index = session.query(ScheduleItem).filter(ScheduleItem.schedule_id == schedule.id).count()
  created = []
  for cp_id in sorted(missing_ids):
    new_item: ScheduleItem = create(
      ScheduleItem,
      {
        'index': next_index,
        'schedule_id': schedule.id,
        'operation_type': ScheduleType.COLLECTIONPOINT,
        'start_time_slot': start_time_slot,
        'end_time_slot': end_time_slot,
      },
      session=session,
    )
    create(
      ScheduleItemCollectionPoint,
      {'schedule_item_id': new_item.id, 'collection_point_id': cp_id},
      session=session,
    )
    created.append(new_item)
    next_index += 1

  logger.info(
    'auto_planning: collegati %d punti di ritiro mancanti al borderò %s (ordine %s)',
    len(created),
    schedule.id,
    order.id,
  )
  return created


# ---------------------------------------------------------------------------
# Riordino del borderò (giro per fascia, dal punto in cui si trova il veicolo)
# ---------------------------------------------------------------------------


def _slot_key(item: ScheduleItem) -> tuple:
  return (item.start_time_slot or time.min, item.end_time_slot or time.min)


def _group_by_slot(
  order_stops: list[StopContext],
  cp_stops: list[StopContext],
  dependencies: dict[int, set[int]],
) -> list[tuple[list[StopContext], list[StopContext]]]:
  """Tappe divise per fascia oraria, dalla prima all'ultima della giornata.

  Le consegne stanno nella fascia promessa al cliente. Un punto di ritiro va
  nella fascia più presto tra quelle degli ordini che ne dipendono, così la
  precedenza ritiro-prima-della-consegna resta vera anche quando lo stesso
  ritiro serve ordini di fasce diverse; senza ordini che ne dipendono resta
  nella sua.
  """
  cp_slot = {stop.entity_id: _slot_key(stop.item) for stop in cp_stops}
  for stop in order_stops:
    for cp_id in dependencies.get(stop.item.id, set()):
      if cp_id in cp_slot:
        cp_slot[cp_id] = min(cp_slot[cp_id], _slot_key(stop.item))

  groups: dict[tuple, tuple[list[StopContext], list[StopContext]]] = defaultdict(lambda: ([], []))
  for stop in order_stops:
    groups[_slot_key(stop.item)][0].append(stop)
  for stop in cp_stops:
    groups[cp_slot[stop.entity_id]][1].append(stop)
  return [groups[key] for key in sorted(groups)]


@dataclass
class StopPlan:
  """Esito del calcolo del percorso, applicabile in un secondo momento.

  Il calcolo (geocodifica + OSRM) e l'applicazione sono separati perche' il
  primo e' lento e non deve stare dentro la transazione che tiene il lock del
  veicolo: ``stop_item_ids`` serve a verificare, prima di applicare, che le
  tappe del borderò siano ancora quelle su cui si e' calcolato.
  """

  stop_item_ids: frozenset
  sequence: list[int]
  slot_updates: list[tuple[int, object, object]]


def plan_schedule_stops(schedule: Schedule, session: session_type) -> StopPlan | None:
  """Calcola l'ordine di visita ottimale delle tappe del borderò, senza scrivere nulla.

  Include sia le tappe ``ORDER`` che ``CollectionPoint``, rispettando la
  precedenza "ritiro prima delle consegne che ne dipendono" (vedi docstring
  del modulo e ``sequencing.py``).

  Le attività libere (``ACTIVITY``) e le tappe già completate non partecipano
  al riordino: restano nella posizione in cui sono e le tappe da fare si
  distribuiscono nei posti rimasti.
  """
  rows = sorted(get_schedule_items(schedule, session=session), key=lambda row: row[0].index)

  # Anche le tappe completate: l'ultima fatta e' il punto da cui riparte il giro.
  order_ids = [sio.order_id for _item, _scp, sio in rows if sio]
  cp_ids = [scp.collection_point_id for _item, scp, _sio in rows if scp]
  orders_by_id = {o.id: o for o in get_by_ids(Order, order_ids, session=session)} if order_ids else {}
  cps_by_id = {cp.id: cp for cp in get_by_ids(CollectionPoint, cp_ids, session=session)} if cp_ids else {}

  raw_stops = []
  done_stops = []
  for item, scp, sio in rows:
    if sio and sio.order_id in orders_by_id:
      order = orders_by_id[sio.order_id]
      stored = (order.address_lat, order.address_lon)
      stop = ('order', item, order.address, order.cap, stored, order.id, order)
    elif scp and scp.collection_point_id in cps_by_id:
      cp = cps_by_id[scp.collection_point_id]
      stop = ('collection_point', item, cp.address, cp.cap, (cp.lat, cp.lon), cp.id, None)
    else:
      continue
    (done_stops if item.completed else raw_stops).append(stop)

  if len(raw_stops) < 2:
    return None

  # Risoluzione concorrente delle coordinate delle tappe e del punto di partenza
  start_stop = _start_stop(schedule, done_stops, session)
  coords = resolve_stop_coords([(s[2], s[3], s[4]) for s in raw_stops] + ([start_stop] if start_stop else []))
  start_coord = coords.pop() if start_stop else None

  order_stops: list[StopContext] = []
  cp_stops: list[StopContext] = []
  dependencies: dict[int, set[int]] = {}

  for (kind, item, _, _, _, entity_id, order), coord in zip(raw_stops, coords):
    stop = StopContext(item=item, kind=kind, coord=coord, entity_id=entity_id)
    if kind == 'order':
      order_stops.append(stop)
      dependencies[item.id] = required_collection_point_ids_for_order(order, session)
    else:
      cp_stops.append(stop)

  # Una sola matrice di durate per tutto il borderò (una chiamata OSRM): il
  # primo punto e' quello da cui parte il veicolo, se si sa.
  located = [stop for stop in cp_stops + order_stops if stop.coord is not None]
  offset = 1 if start_coord else 0
  matrix = duration_matrix(([start_coord] if start_coord else []) + [stop.coord for stop in located])
  matrix_index = {stop.item.id: offset + position for position, stop in enumerate(located)}
  current = 0 if start_coord else None

  # Le fasce si visitano in ordine cronologico e il giro di una riparte da
  # dove e' finito quello della fascia prima.
  # Un ritiro anticipato alla fascia di un ordine più presto ne prende anche
  # l'orario, così il borderò non mostra in testa un ritiro "11:30-12:30".
  final_sequence = []
  slot_updates = []
  for slot_orders, slot_cps in _group_by_slot(order_stops, cp_stops, dependencies):
    for stop in slot_cps:
      if slot_orders and _slot_key(stop.item) != _slot_key(slot_orders[0].item):
        slot_item = slot_orders[0].item
        slot_updates.append((stop.item.id, slot_item.start_time_slot, slot_item.end_time_slot))
    slot_sequence = _sequence_slot(slot_orders, slot_cps, dependencies, matrix, matrix_index, current)
    final_sequence += slot_sequence
    reached = [matrix_index[stop.item.id] for stop in slot_sequence if stop.item.id in matrix_index]
    if reached:
      current = reached[-1]

  return StopPlan(
    stop_item_ids=frozenset(stop.item.id for stop in final_sequence),
    sequence=[stop.item.id for stop in final_sequence],
    slot_updates=slot_updates,
  )


def _start_stop(schedule: Schedule, done_stops: list[tuple], session: session_type) -> tuple | None:
  """Da dove parte il giro, come ``(indirizzo, cap, coordinate salvate)``.

  L'ultima tappa gia' fatta se il giro e' iniziato, altrimenti il deposito del
  veicolo. None se il veicolo non ha ne' indirizzo ne' CAP: il giro parte allora
  dalla tappa che lo rende più corto.
  """
  if done_stops:
    _kind, _item, address, cap, stored, _entity_id, _order = done_stops[-1]
    return (address, cap, stored)
  transport = session.get(Transport, schedule.transport_id)
  if transport and (transport.address or transport.cap):
    return (transport.address, transport.cap, (None, None))
  return None


def _sequence_slot(
  orders: list[StopContext],
  cps: list[StopContext],
  dependencies: dict[int, set[int]],
  matrix: list[list[float]],
  matrix_index: dict[int, int],
  start: int | None,
) -> list[StopContext]:
  """Giro di una fascia da ``start``: ogni ritiro prima delle consegne che ne dipendono.

  I ritiri di cui ha bisogno un ordine ma che stanno in una fascia prima sono
  già fatti e non vincolano nulla. Le tappe senza coordinate restano ai bordi:
  ritiri in testa (la precedenza resta vera), consegne in coda.
  """
  cp_index = {stop.entity_id: matrix_index[stop.item.id] for stop in cps if stop.item.id in matrix_index}
  predecessors = {
    matrix_index[stop.item.id]: {cp_index[cp_id] for cp_id in dependencies.get(stop.item.id, set()) & cp_index.keys()}
    for stop in orders
    if stop.item.id in matrix_index
  }
  stop_by_index = {matrix_index[stop.item.id]: stop for stop in cps + orders if stop.item.id in matrix_index}
  route = sequence_stops(matrix, list(stop_by_index), start, predecessors)
  return (
    [stop for stop in cps if stop.item.id not in matrix_index]
    + [stop_by_index[index] for index in route]
    + [stop for stop in orders if stop.item.id not in matrix_index]
  )


def current_stop_item_ids(schedule: Schedule, session: session_type) -> frozenset:
  """Le tappe che ``plan_schedule_stops`` riordinerebbe ora (per verificare un piano calcolato prima)."""
  return frozenset(
    item.id for item, scp, sio in get_schedule_items(schedule, session=session) if (scp or sio) and not item.completed
  )


def apply_stop_plan(schedule: Schedule, plan: StopPlan, session: session_type) -> None:
  """Scrive nel borderò l'ordine di visita calcolato da ``plan_schedule_stops``."""
  rows = get_schedule_items(schedule, session=session)
  items_by_id = {item.id: item for item, _scp, _sio in rows}

  for item_id, start_time_slot, end_time_slot in plan.slot_updates:
    update(items_by_id[item_id], {'start_time_slot': start_time_slot, 'end_time_slot': end_time_slot}, session=session)

  positions = [
    position
    for position, item in enumerate(sorted(items_by_id.values(), key=lambda item: item.index))
    if item.id in plan.stop_item_ids
  ]
  for new_index, item_id in zip(positions, plan.sequence):
    item = items_by_id[item_id]
    if item.index != new_index:
      update(item, {'index': new_index}, session=session)


def optimize_schedule_stops(schedule: Schedule, session: session_type) -> None:
  """Ricalcola e applica l'``index`` di visita ottimale per le tappe da fare del borderò."""
  plan = plan_schedule_stops(schedule, session)
  if plan:
    apply_stop_plan(schedule, plan, session)

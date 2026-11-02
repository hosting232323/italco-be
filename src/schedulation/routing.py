"""Collegamento dei punti di ritiro agli ordini e riordino del borderò via OSRM.

Ogni prodotto di un ordine può richiedere il ritiro presso un ``CollectionPoint``
(``Product.collection_point_id``). Un ordine può quindi dipendere da più punti di
ritiro, e più ordini possono condividere lo stesso punto di ritiro: in quel caso la
tappa ``CollectionPoint`` nel borderò va creata una sola volta e riusata.

Per ordinare le tappe del borderò (``ScheduleItem``) si usa OSRM Trip Service
(TSP su percorso aperto). OSRM non supporta vincoli di precedenza nativi, quindi
non possiamo semplicemente chiedergli l'ordine ottimale su tutte le tappe insieme:
un ordine potrebbe uscire prima del punto di ritiro da cui dipende. La soluzione è
"trip per cluster + merge":

1. Si raggruppano le tappe in cluster per componente connessa del grafo di
   dipendenza (ordine <-> punto di ritiro richiesto). Ordini senza dipendenze
   formano cluster singoli.
2. Dentro ogni cluster si ottimizzano separatamente i punti di ritiro e gli
   ordini (via OSRM), poi si concatenano ritiri-prima-di-ordini: la precedenza è
   garantita per costruzione, non da un aggiustamento a posteriori.
3. I cluster vengono a loro volta ordinati tra loro via OSRM (usando come ancora
   la prima tappa geocodificabile di ciascuno) e concatenati.

Tutto questo avviene fascia oraria per fascia oraria, in ordine cronologico: le
consegne sono promesse al cliente in una fascia e OSRM non conosce gli orari,
quindi il percorso si ottimizza dentro ogni fascia e le fasce si concatenano.

Se OSRM non è raggiungibile o una tappa non è geocodificabile, si degrada
mantenendo l'ordine relativo originale invece di far fallire la richiesta.
"""

from concurrent.futures import ThreadPoolExecutor
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
)
from ..end_points.orders.queries import query_products
from ..end_points.schedule.preload import preloaded_pickup_ids_for_order
from ..end_points.schedule.queries import get_schedule_items, schedule_has_started
from ..end_points.service.travel import get_lat_lon_by_cap, trip_order_osrm
from ..utils.caps import get_lat_lon_by_address

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
# Riordino del borderò (trip per cluster + merge)
# ---------------------------------------------------------------------------


def _coord_for(address: str | None, cap: str | None, stored: tuple = (None, None)) -> Coord | None:
  """Coordinata di una tappa: quella salvata se c'e', poi l'indirizzo completo se
  geocodificabile, altrimenti il centroide del CAP.

  Il CAP da solo tratterebbe come "vicini" ordini/punti di ritiro distanti
  chilometri ma nello stesso CAP (frequente nei CAP che coprono più comuni o
  zone rurali), falsando l'ordine di visita calcolato da OSRM.
  """
  if stored[0] is not None and stored[1] is not None:
    return stored
  if address:
    lat, lon = get_lat_lon_by_address(address)
    if lat is not None:
      return (lat, lon)
  lat, lon = get_lat_lon_by_cap(cap or '')
  return (lat, lon) if lat is not None else None


def _osrm_or_original_order(n: int, coords: list[Coord | None]) -> list[int]:
  """Indici 0..n-1 nell'ordine ottimale OSRM, o nell'ordine originale come fallback.

  Le tappe senza coordinate (geocoding fallito) vengono accodate in fondo,
  nel loro ordine relativo originale, invece di far fallire il riordino.
  """
  if n <= 1:
    return list(range(n))

  valid = [(i, c) for i, c in enumerate(coords) if c is not None]
  if len(valid) < 2:
    return list(range(n))

  valid_indices = [i for i, _ in valid]
  valid_coords = [c for _, c in valid]
  trip_order = trip_order_osrm(valid_coords)
  if trip_order is None:
    return list(range(n))

  ordered = [valid_indices[i] for i in trip_order]
  missing = [i for i in range(n) if coords[i] is None]
  return ordered + missing


def _build_clusters(
  order_stops: list[StopContext],
  cp_stops: list[StopContext],
  dependencies: dict[int, set[int]],
) -> list[tuple[list[StopContext], list[StopContext]]]:
  """Raggruppa le tappe per componente connessa del grafo ordine<->punto di ritiro.

  ``dependencies`` mappa ``ScheduleItem.id`` di una tappa ordine ai
  ``collection_point_id`` da cui dipende. Ordini senza dipendenze restano soli
  nel proprio cluster.
  """
  cp_by_id = {s.entity_id: s for s in cp_stops}
  parent = {s.item.id: s.item.id for s in order_stops + cp_stops}

  def find(x):
    while parent[x] != x:
      parent[x] = parent[parent[x]]
      x = parent[x]
    return x

  def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb:
      parent[ra] = rb

  for order_stop in order_stops:
    for cp_id in dependencies.get(order_stop.item.id, set()):
      cp_stop = cp_by_id.get(cp_id)
      if cp_stop:
        union(order_stop.item.id, cp_stop.item.id)

  groups: dict[int, list[StopContext]] = defaultdict(list)
  for stop in order_stops + cp_stops:
    groups[find(stop.item.id)].append(stop)

  return [
    ([s for s in group if s.kind == 'collection_point'], [s for s in group if s.kind == 'order'])
    for group in groups.values()
  ]


def _resolve_stop_coords(
  stops: list[tuple[str | None, str | None, tuple]], max_workers: int = 10
) -> list[Coord | None]:
  if not stops:
    return []
  workers = min(max_workers, len(stops))
  with ThreadPoolExecutor(max_workers=workers) as executor:
    return list(executor.map(lambda stop: _coord_for(*stop), stops))


def _order_cluster(cps: list[StopContext], orders: list[StopContext]) -> list[StopContext]:
  """Ordina un cluster: punti di ritiro (ottimizzati tra loro) poi ordini (ottimizzati tra loro)."""
  if len(cps) > 1 and len(orders) > 1:
    with ThreadPoolExecutor(max_workers=2) as executor:
      fut_cp = executor.submit(_osrm_or_original_order, len(cps), [s.coord for s in cps])
      fut_order = executor.submit(_osrm_or_original_order, len(orders), [s.coord for s in orders])
      cp_order = fut_cp.result()
      order_order = fut_order.result()
  else:
    cp_order = _osrm_or_original_order(len(cps), [s.coord for s in cps])
    order_order = _osrm_or_original_order(len(orders), [s.coord for s in orders])
  return [cps[i] for i in cp_order] + [orders[i] for i in order_order]


def _first_coord(stops: list[StopContext]) -> Coord | None:
  return next((s.coord for s in stops if s.coord is not None), None)


def _sequence_stops(
  order_stops: list[StopContext],
  cp_stops: list[StopContext],
  dependencies: dict[int, set[int]],
) -> list[StopContext]:
  """Ordine di visita di un gruppo di tappe: trip per cluster + merge (vedi docstring del modulo)."""
  clusters = _build_clusters(order_stops, cp_stops, dependencies)
  if len(clusters) > 1:
    with ThreadPoolExecutor(max_workers=min(10, len(clusters))) as executor:
      cluster_sequences = list(executor.map(lambda c: _order_cluster(c[0], c[1]), clusters))
  else:
    cluster_sequences = [_order_cluster(cps, orders) for cps, orders in clusters]

  anchors = [_first_coord(sequence) for sequence in cluster_sequences]
  cluster_order = _osrm_or_original_order(len(cluster_sequences), anchors)
  return [stop for ci in cluster_order for stop in cluster_sequences[ci]]


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
  del modulo per l'algoritmo trip-per-cluster-e-merge).

  Le attività libere (``ACTIVITY``) e le tappe già completate non partecipano
  al riordino: restano nella posizione in cui sono e le tappe da fare si
  distribuiscono nei posti rimasti.
  """
  rows = get_schedule_items(schedule, session=session)

  order_ids = [sio.order_id for item, _scp, sio in rows if sio and not item.completed]
  cp_ids = [scp.collection_point_id for item, scp, _sio in rows if scp and not item.completed]
  orders_by_id = {o.id: o for o in get_by_ids(Order, order_ids, session=session)} if order_ids else {}
  cps_by_id = {cp.id: cp for cp in get_by_ids(CollectionPoint, cp_ids, session=session)} if cp_ids else {}

  raw_stops = []
  for item, scp, sio in rows:
    if item.completed:
      continue
    if sio and sio.order_id in orders_by_id:
      order = orders_by_id[sio.order_id]
      stored = (order.address_lat, order.address_lon)
      raw_stops.append(('order', item, order.address, order.cap, stored, order.id, order))
    elif scp and scp.collection_point_id in cps_by_id:
      cp = cps_by_id[scp.collection_point_id]
      raw_stops.append(('collection_point', item, cp.address, cp.cap, (cp.lat, cp.lon), cp.id, None))

  if len(raw_stops) < 2:
    return None

  # Risoluzione concorrente delle coordinate delle tappe
  coords = _resolve_stop_coords([(s[2], s[3], s[4]) for s in raw_stops])

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

  # Le fasce si visitano in ordine cronologico: OSRM ottimizza il percorso
  # dentro ciascuna, mai a cavallo tra due (un ordine delle 9:40 non può
  # finire dopo uno delle 11:30 solo perché è più comodo come strada).
  # Un ritiro anticipato alla fascia di un ordine più presto ne prende anche
  # l'orario, così il borderò non mostra in testa un ritiro "11:30-12:30".
  final_sequence = []
  slot_updates = []
  for slot_orders, slot_cps in _group_by_slot(order_stops, cp_stops, dependencies):
    for stop in slot_cps:
      if slot_orders and _slot_key(stop.item) != _slot_key(slot_orders[0].item):
        slot_item = slot_orders[0].item
        slot_updates.append((stop.item.id, slot_item.start_time_slot, slot_item.end_time_slot))
    final_sequence += _sequence_stops(slot_orders, slot_cps, dependencies)

  return StopPlan(
    stop_item_ids=frozenset(stop.item.id for stop in final_sequence),
    sequence=[stop.item.id for stop in final_sequence],
    slot_updates=slot_updates,
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

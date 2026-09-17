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

Se OSRM non è raggiungibile o una tappa non è geocodificabile, si degrada
mantenendo l'ordine relativo originale invece di far fallire la richiesta.
"""

import logging
from dataclasses import dataclass
from collections import defaultdict

from sqlalchemy.orm import Session as session_type

from database_api.operations import create, update, get_by_ids
from ..database.enum import ScheduleType
from ..database.schema import (
  CollectionPoint,
  Order,
  Schedule,
  ScheduleItem,
  ScheduleItemCollectionPoint,
)
from ..end_points.orders.queries import query_products
from ..end_points.schedule.queries import get_schedule_items
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
  """Punti di ritiro richiesti da ``order``, dedotti dai suoi prodotti."""
  return {p.collection_point_id for p in query_products(order, session=session) if p.collection_point_id}


def link_missing_collection_points(
  order: Order,
  schedule: Schedule,
  start_time_slot,
  end_time_slot,
  session: session_type,
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

  Returns:
    Le nuove ``ScheduleItem`` create (lista vuota se non serviva nulla).
  """
  required_ids = required_collection_point_ids_for_order(order, session)
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


def _coord_for(address: str | None, cap: str | None) -> Coord | None:
  """Coordinata di una tappa: indirizzo completo se geocodificabile, altrimenti centroide del CAP.

  Il CAP da solo tratterebbe come "vicini" ordini/punti di ritiro distanti
  chilometri ma nello stesso CAP (frequente nei CAP che coprono più comuni o
  zone rurali), falsando l'ordine di visita calcolato da OSRM.
  """
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


def _order_cluster(cps: list[StopContext], orders: list[StopContext]) -> list[StopContext]:
  """Ordina un cluster: punti di ritiro (ottimizzati tra loro) poi ordini (ottimizzati tra loro)."""
  cp_order = _osrm_or_original_order(len(cps), [s.coord for s in cps])
  order_order = _osrm_or_original_order(len(orders), [s.coord for s in orders])
  return [cps[i] for i in cp_order] + [orders[i] for i in order_order]


def _first_coord(stops: list[StopContext]) -> Coord | None:
  return next((s.coord for s in stops if s.coord is not None), None)


def optimize_schedule_stops(schedule: Schedule, session: session_type) -> None:
  """Ricalcola e applica l'``index`` di visita ottimale per tutte le tappe del borderò.

  Include sia le tappe ``ORDER`` che ``CollectionPoint``, rispettando la
  precedenza "ritiro prima delle consegne che ne dipendono" (vedi docstring
  del modulo per l'algoritmo trip-per-cluster-e-merge).
  """
  rows = get_schedule_items(schedule, session=session)

  order_ids = [sio.order_id for _item, _scp, sio in rows if sio]
  cp_ids = [scp.collection_point_id for _item, scp, _sio in rows if scp]
  orders_by_id = {o.id: o for o in get_by_ids(Order, order_ids, session=session)} if order_ids else {}
  cps_by_id = {cp.id: cp for cp in get_by_ids(CollectionPoint, cp_ids, session=session)} if cp_ids else {}

  order_stops: list[StopContext] = []
  cp_stops: list[StopContext] = []
  dependencies: dict[int, set[int]] = {}

  for item, scp, sio in rows:
    if sio and sio.order_id in orders_by_id:
      order = orders_by_id[sio.order_id]
      order_stops.append(
        StopContext(item=item, kind='order', coord=_coord_for(order.address, order.cap), entity_id=order.id)
      )
      dependencies[item.id] = required_collection_point_ids_for_order(order, session)
    elif scp and scp.collection_point_id in cps_by_id:
      cp = cps_by_id[scp.collection_point_id]
      cp_stops.append(
        StopContext(item=item, kind='collection_point', coord=_coord_for(cp.address, cp.cap), entity_id=cp.id)
      )

  if len(order_stops) + len(cp_stops) < 2:
    return

  clusters = _build_clusters(order_stops, cp_stops, dependencies)
  cluster_sequences = [_order_cluster(cps, orders) for cps, orders in clusters]

  anchors = [_first_coord(sequence) for sequence in cluster_sequences]
  cluster_order = _osrm_or_original_order(len(cluster_sequences), anchors)
  final_sequence = [stop for ci in cluster_order for stop in cluster_sequences[ci]]

  for new_index, stop in enumerate(final_sequence):
    if stop.item.index != new_index:
      update(stop.item, {'index': new_index}, session=session)

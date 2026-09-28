"""Pianificazione automatica del borderò alla creazione dell'ordine.

Quando la company ha ``automatic_planning == True`` e un ordine viene creato
con fascia oraria già assegnata (``delivery_slot_start`` / ``delivery_slot_end``),
questo modulo si occupa di:

1. Trovare il ``DeliveryCoverageEntry`` che ha generato quella fascia
   (stesso ``transport_id``, stesso giorno della settimana, stesso orario).
2. Trovare o creare lo ``Schedule`` (borderò) per quella data e quel veicolo.
3. Inserire l'ordine come nuova tappa dello ``Schedule``, collegando anche gli
   eventuali punti di ritiro richiesti dai suoi prodotti (vedi ``routing.py``).
4. Riordinare tutte le tappe del borderò con il motore di routing OSRM (Trip
   Service), rispettando la precedenza "ritiro prima delle consegne che ne
   dipendono" (vedi ``routing.optimize_schedule_stops``).

La funzione di ingresso è ``auto_plan_order``, da chiamare dentro la sessione
di ``create_order`` dopo il commit iniziale dell'ordine.
"""

import logging

from sqlalchemy.orm import Session as session_type

from database_api.operations import create, delete, update
from ..database.enum import OrderStatus, ScheduleType
from ..database.schema import (
  DeliveryCoverageEntry,
  DeliveryCoverageCap,
  Order,
  Schedule,
  ScheduleItem,
  ScheduleItemOrder,
)
from ..end_points.rae.product import emit_rae_products
from ..end_points.orders.queries import query_products
from ..end_points.schedule.queries import get_schedule_items
from .routing import link_missing_collection_points, optimize_schedule_stops, required_collection_point_ids_for_order

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lookup fascia di copertura
# ---------------------------------------------------------------------------


def find_coverage_entry(order: Order, session: session_type) -> DeliveryCoverageEntry | None:
  """Restituisce il ``DeliveryCoverageEntry`` corrispondente alla fascia dell'ordine.

  L'ordine porta il veicolo scelto alla creazione (``delivery_transport_id``):
  il blocco e' quello di quel veicolo, stesso giorno della settimana della
  ``dpc`` e stessa fascia. Senza veicolo (ordini creati prima che si
  salvasse) si ricade sui blocchi che coprono il ``cap``, nell'ordine di
  priorita' del riempimento e non nell'ordine che capita al database.
  """
  if not order.dpc or not order.delivery_slot_start or not order.delivery_slot_end:
    return None

  day_of_week = order.dpc.weekday()
  slot = (
    DeliveryCoverageEntry.day_of_week == day_of_week,
    DeliveryCoverageEntry.start_time == order.delivery_slot_start,
    DeliveryCoverageEntry.end_time == order.delivery_slot_end,
  )
  by_priority = (DeliveryCoverageEntry.transport_id, DeliveryCoverageEntry.id)

  if order.delivery_transport_id:
    return (
      session.query(DeliveryCoverageEntry)
      .filter(*slot, DeliveryCoverageEntry.transport_id == order.delivery_transport_id)
      .order_by(*by_priority)
      .first()
    )

  if not order.cap:
    return None

  entry = (
    session.query(DeliveryCoverageEntry)
    .join(DeliveryCoverageCap, DeliveryCoverageCap.entry_id == DeliveryCoverageEntry.id)
    .filter(*slot, DeliveryCoverageCap.cap == order.cap)
    .order_by(*by_priority)
    .first()
  )
  if entry or not order.address:
    return entry

  # Nessun blocco a CAP: l'ordine potrebbe essere coperto da un blocco
  # disegnato sulla mappa (senza CAP salvati), trovato per posizione.
  from ..end_points.delivery_coverage import query_entries_for_polygon_point
  from ..utils.caps import get_lat_lon_by_address

  lat, lon = get_lat_lon_by_address(order.address)
  if lat is None:
    return None

  return next(
    (
      e
      for e in sorted(query_entries_for_polygon_point(lat, lon), key=lambda e: (e.transport_id, e.id))
      if e.day_of_week == day_of_week
      and e.start_time == order.delivery_slot_start
      and e.end_time == order.delivery_slot_end
    ),
    None,
  )


# ---------------------------------------------------------------------------
# Trova o crea il borderò (Schedule)
# ---------------------------------------------------------------------------


def find_or_create_schedule(entry: DeliveryCoverageEntry, order: Order, session: session_type) -> tuple[Schedule, bool]:
  """Restituisce lo ``Schedule`` per ``(order.dpc, entry.transport_id)``.

  Se non esiste ne crea uno nuovo: i corrieri non si assegnano più qui, li
  porta il veicolo (``DeliveryUserInfo.transport_id``).

  Returns:
    (schedule, created): created=True se appena creato, False se già esistente.
  """
  existing = (
    session.query(Schedule)
    .filter(
      Schedule.date == order.dpc,
      Schedule.transport_id == entry.transport_id,
    )
    .first()
  )
  if existing:
    return existing, False

  schedule: Schedule = create(
    Schedule,
    {'date': order.dpc, 'transport_id': entry.transport_id},
    session=session,
  )
  return schedule, True


# ---------------------------------------------------------------------------
# Inserimento tappa nel borderò
# ---------------------------------------------------------------------------


def insert_order_into_schedule(
  order: Order,
  schedule: Schedule,
  entry: DeliveryCoverageEntry,
  session: session_type,
) -> tuple[ScheduleItem, list[tuple[Order, ScheduleItem]]]:
  """Inserisce ``order`` nello ``Schedule``.

  1. Crea il nuovo ``ScheduleItem`` (ORDER) + ``ScheduleItemOrder``, in coda.
  2. Collega i punti di ritiro richiesti dai prodotti dell'ordine, riusando
     quelli già presenti nel borderò per altri ordini.
  3. Ricalcola l'ordine di visita di tutte le tappe (ordini + punti di ritiro)
     via OSRM Trip Service.
  4. Aggiorna lo stato dell'ordine (SCHEDULED o BOOKING).

  Returns:
    (nuovo ScheduleItem, lista (Order, ScheduleItem) per gli SMS post-commit).
  """
  existing_stops_count = session.query(ScheduleItem).filter(ScheduleItem.schedule_id == schedule.id).count()

  new_item: ScheduleItem = create(
    ScheduleItem,
    {
      'index': existing_stops_count,
      'schedule_id': schedule.id,
      'operation_type': ScheduleType.ORDER,
      'start_time_slot': entry.start_time,
      'end_time_slot': entry.end_time,
    },
    session=session,
  )

  create(
    ScheduleItemOrder,
    {'order_id': order.id, 'schedule_item_id': new_item.id},
    session=session,
  )

  link_missing_collection_points(order, schedule, entry.start_time, entry.end_time, session=session)
  optimize_schedule_stops(schedule, session=session)

  # Stato ordine: BOOKING se tutti i prodotti hanno veicolo, altrimenti SCHEDULED
  products = query_products(order, session=session)
  new_status = OrderStatus.BOOKING if products and all(p.transport_id for p in products) else OrderStatus.SCHEDULED
  update(order, {'status': new_status}, session=session)

  # Prodotti RAE
  emit_rae_products(order, schedule, session=session)

  return new_item, [(order, new_item)]


# ---------------------------------------------------------------------------
# Rimozione dal borderò (cambio di data/zona)
# ---------------------------------------------------------------------------


def unplan_order(order: Order, session: session_type) -> None:
  """Toglie l'ordine dai borderò in cui e' una tappa, lasciandoli coerenti.

  Serve quando il cliente cambia data o zona di un ordine gia' pianificato: la
  tappa vecchia non deve restare nel borderò della data di prima. L'ordine
  torna in attesa (stesso effetto della rimozione manuale dal borderò), i
  punti di ritiro che servivano solo a lui escono con lui e le tappe rimaste
  vengono rinumerate e riordinate.
  """
  from ..end_points.schedule.utils import delete_schedule_items

  rows = (
    session.query(ScheduleItem, ScheduleItemOrder)
    .join(ScheduleItemOrder, ScheduleItemOrder.schedule_item_id == ScheduleItem.id)
    .filter(ScheduleItemOrder.order_id == order.id, ScheduleItem.operation_type == ScheduleType.ORDER)
    .all()
  )
  if not rows:
    return

  schedule_ids = {item.schedule_id for item, _ in rows}
  pickup_ids = required_collection_point_ids_for_order(order, session)
  delete_schedule_items([(item, None, sio) for item, sio in rows], session=session)
  session.flush()

  for schedule_id in schedule_ids:
    schedule = session.get(Schedule, schedule_id)
    _drop_orphan_pickups(schedule, pickup_ids, session)
    _renumber_stops(schedule, session)
    optimize_schedule_stops(schedule, session=session)


def _drop_orphan_pickups(schedule: Schedule, pickup_ids: set[int], session: session_type) -> None:
  if not pickup_ids:
    return
  rows = get_schedule_items(schedule, session=session)
  still_needed: set[int] = set()
  for _item, _scp, sio in rows:
    if sio:
      remaining = session.get(Order, sio.order_id)
      still_needed |= required_collection_point_ids_for_order(remaining, session)
  for item, scp, _sio in rows:
    if scp and scp.collection_point_id in pickup_ids and scp.collection_point_id not in still_needed:
      delete(scp, session=session)
      delete(item, session=session)
  session.flush()


def _renumber_stops(schedule: Schedule, session: session_type) -> None:
  items = session.query(ScheduleItem).filter(ScheduleItem.schedule_id == schedule.id).order_by(ScheduleItem.index).all()
  for new_index, item in enumerate(items):
    if item.index != new_index:
      update(item, {'index': new_index}, session=session)


# ---------------------------------------------------------------------------
# Entrypoint pubblico
# ---------------------------------------------------------------------------


def auto_plan_order(order: Order, session: session_type) -> list[tuple[Order, ScheduleItem]]:
  """Pianifica automaticamente ``order`` nel borderò corretto.

  Deve essere chiamato **dopo** ``session.flush()`` (l'ordine deve avere id)
  ma **prima** di ``session.commit()`` così tutto avviene nella stessa transazione.

  Returns:
    Lista di (Order, ScheduleItem) che necessitano di SMS post-commit.
    Lista vuota se la pianificazione non è applicabile o fallisce.
  """
  if not order.delivery_slot_start or not order.delivery_slot_end:
    logger.debug('auto_planning: ordine %s senza fascia oraria, skip', order.id)
    return []

  entry = find_coverage_entry(order, session)
  if not entry:
    logger.warning(
      'auto_planning: nessuna DeliveryCoverageEntry trovata per ordine %s (cap=%s, dpc=%s, slot=%s-%s)',
      order.id,
      order.cap,
      order.dpc,
      order.delivery_slot_start,
      order.delivery_slot_end,
    )
    return []

  schedule, created = find_or_create_schedule(entry, order, session)
  logger.info(
    'auto_planning: borderò %s=%s per ordine %s (veicolo=%s, data=%s)',
    'creato' if created else 'trovato',
    schedule.id,
    order.id,
    entry.transport_id,
    order.dpc,
  )

  _new_item, pending_sms = insert_order_into_schedule(order, schedule, entry, session)
  return pending_sms

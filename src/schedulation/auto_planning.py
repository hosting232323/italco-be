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

from database_api.operations import create, update
from ..database.enum import OrderStatus, ScheduleType
from ..database.schema import (
  DeliveryCoverageEntry,
  DeliveryCoverageCap,
  DeliveryGroup,
  DeliveryUserInfo,
  Order,
  Schedule,
  ScheduleItem,
  ScheduleItemOrder,
)
from ..end_points.rae.product import emit_rae_products
from ..end_points.orders.queries import query_products
from .routing import link_missing_collection_points, optimize_schedule_stops

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lookup fascia di copertura
# ---------------------------------------------------------------------------


def find_coverage_entry(order: Order, session: session_type) -> DeliveryCoverageEntry | None:
  """Restituisce il ``DeliveryCoverageEntry`` corrispondente alla fascia dell'ordine.

  Criteri:
  - stesso giorno della settimana della ``dpc``
  - stesso ``start_time`` e ``end_time`` della fascia assegnata all'ordine
  - copre il ``cap`` dell'ordine
  """
  if not order.dpc or not order.delivery_slot_start or not order.delivery_slot_end or not order.cap:
    return None

  day_of_week = order.dpc.weekday()

  entry = (
    session.query(DeliveryCoverageEntry)
    .join(DeliveryCoverageCap, DeliveryCoverageCap.entry_id == DeliveryCoverageEntry.id)
    .filter(
      DeliveryCoverageEntry.day_of_week == day_of_week,
      DeliveryCoverageEntry.start_time == order.delivery_slot_start,
      DeliveryCoverageEntry.end_time == order.delivery_slot_end,
      DeliveryCoverageCap.cap == order.cap,
    )
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
      for e in query_entries_for_polygon_point(lat, lon)
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

  Se non esiste ne crea uno nuovo e assegna i delivery users collegati al
  veicolo come ``DeliveryGroup``.

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

  # Associa i corrieri del veicolo al borderò
  delivery_user_ids = [
    row.user_id
    for row in session.query(DeliveryUserInfo.user_id)
    .filter(
      DeliveryUserInfo.transport_id == entry.transport_id,
      DeliveryUserInfo.user_id.isnot(None),
    )
    .all()
  ]
  for uid in delivery_user_ids:
    create(DeliveryGroup, {'schedule_id': schedule.id, 'user_id': uid}, session=session)

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

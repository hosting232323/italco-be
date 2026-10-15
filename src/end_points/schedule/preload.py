"""Precarico: ritiro dei prodotti il giorno prima della consegna.

Il precarico vale solo se due cose sono vere insieme:

- il punto di ritiro del prodotto ammette il precarico
  (``CollectionPoint.preloaded``);
- l'indirizzo dell'ordine e' un'area di precarico per quel punto: se il punto ha
  aree proprie (``CollectionPointPreloadArea``, per CAP o poligono) l'indirizzo
  deve cadere in una di esse, altrimenti vale l'area di copertura dell'ordine
  (``DeliveryCoverageEntry.accepts_preloads``). Le aree del punto prevalgono
  sull'area di copertura, in entrambi i sensi.

La scelta e' per punto di ritiro, non per ordine: se un ordine ha due prodotti
con due punti diversi e uno solo e' precaricato, quel prodotto si ritira il
giorno prima (tappa del borderò della vigilia dello stesso veicolo), l'altro
normalmente nel borderò della consegna. ``Order.preloaded`` dice solo che
l'ordine ha almeno un prodotto precaricato, lo calcola il server.
"""

from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session as session_type

from database_api import Session

from ...database.schema import (
  CollectionPoint,
  CollectionPointPreloadArea,
  DeliveryCoverageEntry,
  Order,
  Product,
  ScheduleItemOrder,
)
from ...utils.geo import point_in_polygon


def area_contains(area: CollectionPointPreloadArea, cap, lat, lon) -> bool:
  """Se l'indirizzo (CAP e/o coordinate) cade nell'area di precarico."""
  if cap and str(cap).strip() in {str(item).strip() for item in area.caps or []}:
    return True
  if lat is None or lon is None or not area.polygon:
    return False
  return point_in_polygon((lat, lon), area.polygon)


def preloaded_collection_point_ids(
  collection_point_ids, session: session_type, address: tuple | None = None, zone_accepts: bool = True
) -> set[int]:
  """Tra `collection_point_ids`, quelli che ammettono il precarico.

  Con `address` (cap, lat, lon) restano solo i punti per cui quell'indirizzo e'
  da precaricare: se il punto ha aree di precarico l'indirizzo deve cadere in
  una, altrimenti vale `zone_accepts` (l'area di copertura accetta precarichi).
  Senza `address` conta solo il flag del punto.
  """
  ids = {cp_id for cp_id in collection_point_ids if cp_id}
  if not ids:
    return set()
  rows = (
    session.query(CollectionPoint.id).filter(CollectionPoint.id.in_(ids), CollectionPoint.preloaded.is_(True)).all()
  )
  flagged = {row.id for row in rows}
  if address is None or not flagged:
    return flagged

  cap, lat, lon = address
  areas_by_point: dict[int, list[CollectionPointPreloadArea]] = {}
  for area in session.query(CollectionPointPreloadArea).filter(
    CollectionPointPreloadArea.collection_point_id.in_(flagged)
  ):
    areas_by_point.setdefault(area.collection_point_id, []).append(area)
  return {
    cp_id
    for cp_id in flagged
    if (
      any(area_contains(area, cap, lat, lon) for area in areas_by_point[cp_id])
      if cp_id in areas_by_point
      else zone_accepts
    )
  }


def _as_date(value) -> date | None:
  if isinstance(value, datetime):
    return value.date()
  if isinstance(value, date):
    return value
  try:
    return date.fromisoformat(str(value)[:10])
  except ValueError:
    return None


def can_preload_on(dpc, transport_id: int, session: session_type) -> bool:
  """Se il ritiro della vigilia di `dpc` e' eseguibile dal veicolo `transport_id`.

  La vigilia non puo' essere nel passato e il veicolo deve lavorare quel giorno
  (almeno un blocco di copertura nel suo giorno della settimana): altrimenti il
  prodotto si ritira normalmente nel borderò della consegna.
  """
  day = _as_date(dpc)
  if day is None or not transport_id:
    return False
  eve = day - timedelta(days=1)
  if eve < date.today():
    return False
  return (
    session.query(DeliveryCoverageEntry.id)
    .filter(DeliveryCoverageEntry.transport_id == transport_id, DeliveryCoverageEntry.day_of_week == eve.weekday())
    .first()
    is not None
  )


def order_is_preloaded(
  entry: DeliveryCoverageEntry | None,
  collection_point_ids,
  session: session_type,
  dpc=None,
  cap=None,
  lat=None,
  lon=None,
) -> bool:
  """Se un ordine con questi punti di ritiro, preso da `entry`, e' precaricato.

  Con `dpc` verifica anche che la vigilia sia eseguibile (vedi can_preload_on).
  `cap`, `lat`, `lon` sono l'indirizzo di consegna: servono per le aree di
  precarico dei punti. Senza indirizzo vale solo l'area di copertura.
  """
  if entry is None:
    return False
  has_address = any(value is not None for value in (cap, lat, lon))
  if not has_address and not entry.accepts_preloads:
    return False
  if dpc is not None and not can_preload_on(dpc, entry.transport_id, session):
    return False
  address = (cap, lat, lon) if has_address else None
  return bool(
    preloaded_collection_point_ids(
      collection_point_ids, session, address=address, zone_accepts=bool(entry.accepts_preloads)
    )
  )


def preloaded_pickup_ids_for_order(order: Order, session: session_type) -> set[int]:
  """Punti di ritiro dell'ordine il cui ritiro avviene il giorno prima."""
  if not order.preloaded:
    return set()
  from ...schedulation.auto_planning import find_coverage_entry

  ids = {
    row.collection_point_id
    for row in session.query(Product.collection_point_id)
    .filter(Product.order_id == order.id, Product.collection_point_id.isnot(None))
    .all()
  }
  entry = find_coverage_entry(order, session)
  return preloaded_collection_point_ids(
    ids,
    session,
    address=(order.cap, order.address_lat, order.address_lon),
    # Senza fascia trovata non si puo' rileggere la zona: l'ordine e' gia' precaricato,
    # quindi per i punti senza aree vale com'e' stato deciso.
    zone_accepts=bool(entry.accepts_preloads) if entry else True,
  )


def preloaded_products_by_stop(stops, session: session_type) -> dict[tuple, list[tuple[Order, Product]]]:
  """Prodotti da ritirare alle tappe per i precarichi del giorno dopo.

  `stops` sono tuple (data del borderò, veicolo, punto di ritiro): una sola query
  per tutte, non una per tappa. Stesso veicolo, consegna il giorno successivo,
  ordine precaricato e pianificato (un ordine tolto dal borderò non genera ritiri)
  e punto di ritiro che ammette il precarico. Chiave del risultato: la tupla.
  """
  stops = set(stops)
  preloaded_ids = preloaded_collection_point_ids({cp_id for _, _, cp_id in stops}, session)
  stops = {stop for stop in stops if stop[2] in preloaded_ids}
  if not stops:
    return {}
  rows = (
    session.query(Order, Product)
    .join(Product, Product.order_id == Order.id)
    .filter(
      Order.delivery_transport_id.in_({transport_id for _, transport_id, _ in stops}),
      Order.dpc.in_({day + timedelta(days=1) for day, _, _ in stops}),
      Order.preloaded.is_(True),
      Order.id.in_(session.query(ScheduleItemOrder.order_id)),
      Product.collection_point_id.in_(preloaded_ids),
    )
    .order_by(Order.id, Product.id)
    .all()
  )
  result: dict[tuple, list[tuple[Order, Product]]] = {}
  order_pickup_ids: dict[int, set[int]] = {}
  for order, product in rows:
    # Il flag del punto non basta: l'indirizzo dell'ordine deve essere un'area
    # di precarico per quel punto.
    if order.id not in order_pickup_ids:
      order_pickup_ids[order.id] = preloaded_pickup_ids_for_order(order, session)
    if product.collection_point_id not in order_pickup_ids[order.id]:
      continue
    key = (order.dpc - timedelta(days=1), order.delivery_transport_id, product.collection_point_id)
    if key in stops:
      result.setdefault(key, []).append((order, product))
  return result


def _pickup_product(order: dict | Order, name: str, preloaded: bool, collected: bool) -> dict:
  get = order.get if isinstance(order, dict) else lambda key: getattr(order, key, None)
  return {
    'name': name,
    'order_id': get('order_id') or get('id'),
    'addressee': get('addressee'),
    'address': get('address'),
    'cap': get('cap'),
    'preloaded': preloaded,
    'collected': bool(collected),
  }


def annotate_preloads(schedules: list[dict], session: session_type = None) -> list[dict]:
  """Aggiunge ai borderò serializzati le informazioni sul precarico.

  - tappa ``Order``: `preloaded: True` sui prodotti il cui ritiro avviene il
    giorno prima (non c'e' una tappa di ritiro in questo borderò);
  - tappa ``CollectionPoint``: `pickup_products`, i prodotti da ritirare li'
    (quelli degli ordini del borderò e i precarichi del giorno dopo, questi
    ultimi con `preloaded: True`), e `has_preload` se c'e' almeno un precarico.
  """
  if session is None:
    with Session() as own_session:
      return annotate_preloads(schedules, own_session)

  order_pickup_ids: dict[int, set[int]] = {}

  def _pickup_ids(item: dict) -> set[int]:
    order_id = item.get('order_id') or item.get('id')
    if order_id not in order_pickup_ids:
      order = session.get(Order, order_id) if order_id else None
      order_pickup_ids[order_id] = preloaded_pickup_ids_for_order(order, session) if order else set()
    return order_pickup_ids[order_id]

  next_day_products = preloaded_products_by_stop(
    {
      (date.fromisoformat(schedule['date'][:10]), schedule['transport_id'], item['collection_point_id'])
      for schedule in schedules
      for item in schedule['schedule_items']
      if item['operation_type'] == 'CollectionPoint'
    },
    session,
  )

  for schedule in schedules:
    items = schedule['schedule_items']
    for item in items:
      if item['operation_type'] != 'Order':
        continue
      for product in item.get('products', {}).values():
        cp = product.get('collection_point')
        if cp and item.get('preloaded') and cp['id'] in _pickup_ids(item):
          product['preloaded'] = True

    for item in items:
      if item['operation_type'] != 'CollectionPoint':
        continue
      cp_id = item['collection_point_id']
      pickup = [
        _pickup_product(order_item, name, False, product.get('collected'))
        for order_item in items
        if order_item['operation_type'] == 'Order'
        for name, product in order_item.get('products', {}).items()
        if product.get('collection_point', {}).get('id') == cp_id and not product.get('preloaded')
      ]
      schedule_date = date.fromisoformat(schedule['date'][:10])
      for order, product in next_day_products.get((schedule_date, schedule['transport_id'], cp_id), []):
        pickup.append(_pickup_product(order, product.name, True, product.collected))
      item['pickup_products'] = pickup
      item['has_preload'] = any(entry['preloaded'] for entry in pickup)
  return schedules

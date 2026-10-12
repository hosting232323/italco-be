"""Precarico: ritiro dei prodotti il giorno prima della consegna.

Il precarico vale solo se due cose sono vere insieme:

- l'area di copertura dell'ordine accetta precarichi
  (``DeliveryCoverageEntry.accepts_preloads``);
- il punto di ritiro del prodotto ammette il precarico
  (``CollectionPoint.preloaded``).

La scelta e' per punto di ritiro, non per ordine: se un ordine ha due prodotti
con due punti diversi e uno solo e' precaricato, quel prodotto si ritira il
giorno prima (tappa del borderò della vigilia dello stesso veicolo), l'altro
normalmente nel borderò della consegna. ``Order.preloaded`` dice solo che
l'ordine ha almeno un prodotto precaricato, lo calcola il server.
"""

from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session as session_type

from database_api import Session

from ...database.schema import CollectionPoint, DeliveryCoverageEntry, Order, Product, ScheduleItemOrder


def preloaded_collection_point_ids(collection_point_ids, session: session_type) -> set[int]:
  """Tra `collection_point_ids`, quelli che ammettono il precarico."""
  ids = {cp_id for cp_id in collection_point_ids if cp_id}
  if not ids:
    return set()
  rows = (
    session.query(CollectionPoint.id).filter(CollectionPoint.id.in_(ids), CollectionPoint.preloaded.is_(True)).all()
  )
  return {row.id for row in rows}


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
  entry: DeliveryCoverageEntry | None, collection_point_ids, session: session_type, dpc=None
) -> bool:
  """Se un ordine con questi punti di ritiro, preso da `entry`, e' precaricato.

  Con `dpc` verifica anche che la vigilia sia eseguibile (vedi can_preload_on).
  """
  if entry is None or not entry.accepts_preloads:
    return False
  if dpc is not None and not can_preload_on(dpc, entry.transport_id, session):
    return False
  return bool(preloaded_collection_point_ids(collection_point_ids, session))


def preloaded_pickup_ids_for_order(order: Order, session: session_type) -> set[int]:
  """Punti di ritiro dell'ordine il cui ritiro avviene il giorno prima."""
  if not order.preloaded:
    return set()
  ids = {
    row.collection_point_id
    for row in session.query(Product.collection_point_id)
    .filter(Product.order_id == order.id, Product.collection_point_id.isnot(None))
    .all()
  }
  return preloaded_collection_point_ids(ids, session)


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
  for order, product in rows:
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

  cp_ids = {
    product['collection_point']['id']
    for schedule in schedules
    for item in schedule['schedule_items']
    if item['operation_type'] == 'Order'
    for product in item.get('products', {}).values()
    if 'collection_point' in product
  }
  preloaded_ids = preloaded_collection_point_ids(cp_ids, session)
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
        if cp and item.get('preloaded') and cp['id'] in preloaded_ids:
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

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

from datetime import date, timedelta

from sqlalchemy.orm import Session as session_type

from database_api import Session

from ...database.schema import CollectionPoint, DeliveryCoverageEntry, Order, Product


def preloaded_collection_point_ids(collection_point_ids, session: session_type) -> set[int]:
  """Tra `collection_point_ids`, quelli che ammettono il precarico."""
  ids = {cp_id for cp_id in collection_point_ids if cp_id}
  if not ids:
    return set()
  rows = (
    session.query(CollectionPoint.id).filter(CollectionPoint.id.in_(ids), CollectionPoint.preloaded.is_(True)).all()
  )
  return {row.id for row in rows}


def order_is_preloaded(entry: DeliveryCoverageEntry | None, collection_point_ids, session: session_type) -> bool:
  """Se un ordine con questi punti di ritiro, preso da `entry`, e' precaricato."""
  if entry is None or not entry.accepts_preloads:
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


def preloaded_products_for_stop(
  schedule_date: date, transport_id: int, collection_point_id: int, session: session_type
) -> list[tuple[Order, Product]]:
  """Prodotti da ritirare a questa tappa per i precarichi del giorno dopo.

  Stesso veicolo, consegna il giorno successivo a `schedule_date`, ordine
  precaricato e punto di ritiro che ammette il precarico.
  """
  if not preloaded_collection_point_ids([collection_point_id], session):
    return []
  return (
    session.query(Order, Product)
    .join(Product, Product.order_id == Order.id)
    .filter(
      Order.delivery_transport_id == transport_id,
      Order.dpc == schedule_date + timedelta(days=1),
      Order.preloaded.is_(True),
      Product.collection_point_id == collection_point_id,
    )
    .order_by(Order.id, Product.id)
    .all()
  )


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
      for order, product in preloaded_products_for_stop(schedule_date, schedule['transport_id'], cp_id, session):
        pickup.append(_pickup_product(order, product.name, True, product.collected))
      item['pickup_products'] = pickup
      item['has_preload'] = any(entry['preloaded'] for entry in pickup)
  return schedules

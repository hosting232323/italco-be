import logging
from datetime import date, time

import requests
from sqlalchemy.orm import Session as session_type, joinedload

from database_api import Session
from ...database.schema import (
  CollectionPoint,
  Company,
  DeliveryCoverageEntry,
  Order,
  Product,
  Service,
  ServiceUser,
  Transport,
  User,
)
from ...utils.geo import point_in_polygon
from ...utils.caps import get_lat_lon_by_address, get_lat_lon_by_cap

logger = logging.getLogger(__name__)

# Costante temporanea (N): minuti stimati per prodotto con punto di ritiro, in attesa
# di un calcolo reale basato sul percorso verso il punto di ritiro (vedi
# schedulation/routing.py, che oggi lo riordina nel borderò ma non ne stima la durata).
PICKUP_POINT_MINUTES_PER_PRODUCT = 4


def calculate_order_service_duration(order: Order) -> int:
  """Calcola la durata totale dei servizi associati ai prodotti di un ordine (in minuti).

  Usa la durata definita sul Service collegato a ciascun prodotto.
  """
  total = 0
  for product in getattr(order, 'product', []) or []:
    service_user = getattr(product, 'service_user', None)
    service = getattr(service_user, 'service', None) if service_user else None
    if service and getattr(service, 'duration', None) is not None:
      total += service.duration
  return total


def calculate_payload_service_duration(payload: dict, user: User = None, session: session_type = None) -> int:
  """Calcola la durata totale dei servizi a partire da un payload di richiesta

  (es. check-constraints, creazione ordine con 'products' o 'services_id').
  """
  if not payload:
    return 0

  if 'service_duration' in payload and isinstance(payload['service_duration'], int):
    return payload['service_duration']

  products = payload.get('products')
  services_id = payload.get('services_id')

  def _compute(sess: session_type) -> int:
    total = 0
    if isinstance(products, dict) and products:
      for _, product_data in products.items():
        services = product_data.get('services') if isinstance(product_data, dict) else None
        if not isinstance(services, list):
          continue
        for s in services:
          s_id = s.get('id') if isinstance(s, dict) else s
          if not isinstance(s_id, int):
            continue
          service = sess.query(Service).filter(Service.id == s_id).first()
          if service and service.duration is not None:
            total += service.duration
      return total

    if isinstance(services_id, list) and services_id:
      for s_id in services_id:
        if not isinstance(s_id, int):
          continue
        service = sess.query(Service).filter(Service.id == s_id).first()
        if service and service.duration is not None:
          total += service.duration
      return total

    return 0

  if session is not None:
    return _compute(session)
  with Session() as sess:
    return _compute(sess)


def get_entry_capacity_minutes(entry: DeliveryCoverageEntry) -> int:
  """Restituisce la capienza naturale in minuti della fascia (end_time - start_time)."""
  if not entry or not entry.start_time or not entry.end_time:
    return 0
  start_minutes = entry.start_time.hour * 60 + entry.start_time.minute
  end_minutes = entry.end_time.hour * 60 + entry.end_time.minute
  return max(0, end_minutes - start_minutes)


def query_slot_orders(
  entry: DeliveryCoverageEntry, dpc: date, exclude_order_id: int = None, session: session_type = None
) -> list[Order]:
  """Restituisce gli ordini che impegnano la fascia oraria dell'entry nella data dpc."""

  def _query(sess: session_type):
    caps = [cap_obj.cap for cap_obj in getattr(entry, 'caps', [])]
    query = (
      sess.query(Order)
      .options(joinedload(Order.product).joinedload(Product.service_user).joinedload(ServiceUser.service))
      .filter(
        Order.dpc == dpc,
        Order.delivery_slot_start == entry.start_time,
        Order.delivery_slot_end == entry.end_time,
      )
    )
    if caps:
      query = query.filter(Order.cap.in_(caps))
    if exclude_order_id:
      query = query.filter(Order.id != exclude_order_id)
    orders = query.all()

    # Entry disegnato sulla mappa (nessun CAP): senza questo filtro
    # conterebbe TUTTI gli ordini dello stesso giorno/fascia, anche quelli di
    # tutt'altra zona/veicolo che capitano ad avere lo stesso orario.
    if not caps and getattr(entry, 'polygon', None):
      matched = []
      for order in orders:
        lat, lon = get_lat_lon_by_address(order.address)
        if lat is not None and point_in_polygon((lat, lon), entry.polygon):
          matched.append(order)
      orders = matched

    return orders

  if session is not None:
    return _query(session)
  with Session() as sess:
    return _query(sess)


def order_pickup_collection_point_ids(order: Order) -> list[int]:
  """collection_point_id di ciascun prodotto dell'ordine che richiede un ritiro

  (con ripetizioni: un ordine con più prodotti sullo stesso punto lo conta più volte,
  la dedup è compito di chi aggrega più ordini, vedi calculate_orders_pickup_minutes).
  """
  return [
    product.collection_point_id
    for product in getattr(order, 'product', []) or []
    if getattr(product, 'collection_point_id', None)
  ]


def calculate_order_pickup_minutes(order: Order, exclude_collection_point_ids: set[int] = None) -> int:
  """(Costante N temporanea) x numero di prodotti dell'ordine con un punto di ritiro

  non già in ``exclude_collection_point_ids``: un punto di ritiro già coperto da un
  altro ordine della stessa fascia non va ricontato, il veicolo ci passa comunque
  una volta sola.
  """
  excluded = set(exclude_collection_point_ids or [])
  count = sum(1 for cp_id in order_pickup_collection_point_ids(order) if cp_id not in excluded)
  return PICKUP_POINT_MINUTES_PER_PRODUCT * count


def calculate_orders_pickup_minutes(orders: list[Order]) -> int:
  """Minuti dei punti di ritiro per un gruppo di ordini della stessa fascia, deduplicati:

  più ordini sullo stesso punto di ritiro lo contano una volta sola (stesso criterio di
  calculate_order_pickup_minutes, applicato in ordine deterministico su tutto il gruppo).
  """
  seen: set[int] = set()
  total = 0
  for order in sorted(orders, key=lambda o: o.id):
    total += calculate_order_pickup_minutes(order, exclude_collection_point_ids=seen)
    seen.update(order_pickup_collection_point_ids(order))
  return total


def payload_pickup_collection_point_ids(payload_products: dict) -> list[int]:
  """collection_point_id di ciascun prodotto di un payload 'products' non ancora salvato

  (stessa forma di create_order/update_order: {nome: {'collection_point': {'id': ...}, ...}}).
  """
  if not isinstance(payload_products, dict):
    return []
  ids = []
  for product_data in payload_products.values():
    collection_point = product_data.get('collection_point') if isinstance(product_data, dict) else None
    cp_id = collection_point.get('id') if isinstance(collection_point, dict) else None
    if isinstance(cp_id, int):
      ids.append(cp_id)
  return ids


def calculate_payload_pickup_minutes(payload_products: dict, exclude_collection_point_ids: set[int] = None) -> int:
  """(Costante N temporanea) x numero di prodotti del payload con un punto di ritiro

  non già in `exclude_collection_point_ids`: stesso criterio di calculate_order_pickup_minutes,
  applicato a un ordine non ancora salvato (payload di create_order/check-constraints)."""
  excluded = set(exclude_collection_point_ids or [])
  count = sum(1 for cp_id in payload_pickup_collection_point_ids(payload_products) if cp_id not in excluded)
  return PICKUP_POINT_MINUTES_PER_PRODUCT * count


def is_first_entry_of_day(entry: DeliveryCoverageEntry, session: session_type) -> bool:
  """Se ``entry`` e' la prima fascia della giornata di quel veicolo.

  Conta solo per lei la tratta di avvicinamento: nelle fasce successive il
  veicolo e' gia' in giro, arriva dall'ultima tappa della fascia precedente e
  non riparte dal deposito.
  """
  earlier = (
    session.query(DeliveryCoverageEntry.id)
    .filter(
      DeliveryCoverageEntry.transport_id == entry.transport_id,
      DeliveryCoverageEntry.day_of_week == entry.day_of_week,
      DeliveryCoverageEntry.start_time < entry.start_time,
    )
    .first()
  )
  return earlier is None


def _minutes(moment: time) -> int:
  return moment.hour * 60 + moment.minute


def entry_lead_minutes(entry: DeliveryCoverageEntry, session: session_type) -> int:
  """Minuti tra l'apertura dell'attivita' e l'inizio della fascia.

  E' il margine in cui il corriere puo' gia' muoversi senza consumare la
  fascia: se l'attivita' apre alle 9 e la fascia parte alle 10, sono 60 minuti
  per raggiungere i primi ritiri e portarsi verso la prima consegna.

  Zero se la company non ha un orario di apertura (il calcolo resta quello di
  prima: tutto il lavoro in testa pesa sulla fascia) o se la fascia comincia
  gia' all'apertura o prima.
  """
  if entry.start_time is None:
    return 0
  company = session.query(Company).filter(Company.id == entry.company_id).first()
  opening = getattr(company, 'activity_start_time', None)
  if opening is None:
    return 0
  return max(0, _minutes(entry.start_time) - _minutes(opening))


def _front_route_coords(
  orders: list[Order],
  session: session_type,
  new_products: dict = None,
  new_coord: tuple = None,
) -> tuple[list[tuple], list[tuple]]:
  """Le coordinate dei ritiri e delle consegne che il veicolo tocca in testa alla giornata.

  I ritiri sono quelli richiesti dai prodotti degli ordini della fascia (e del
  nuovo ordine, se non ancora salvato); le consegne sono gli indirizzi degli
  ordini, tra cui il veicolo sceglie dove andare dopo l'ultimo ritiro.
  """
  from .travel import get_lat_lon_for_collection_point, get_lat_lon_for_order

  cp_ids = {cp_id for order in orders for cp_id in order_pickup_collection_point_ids(order)}
  cp_ids.update(payload_pickup_collection_point_ids(new_products or {}))

  pickups = []
  if cp_ids:
    points = session.query(CollectionPoint).filter(CollectionPoint.id.in_(sorted(cp_ids))).all()
    pickups = [get_lat_lon_for_collection_point(point) for point in points]

  deliveries = [get_lat_lon_for_order(order) for order in orders]
  if new_coord:
    deliveries.append(new_coord)

  return (
    [(lat, lon) for lat, lon in pickups if lat is not None],
    [(lat, lon) for lat, lon in deliveries if lat is not None],
  )


def entry_front_route_minutes(
  entry: DeliveryCoverageEntry,
  orders: list[Order],
  session: session_type,
  new_products: dict = None,
  new_coord: tuple = None,
) -> int:
  """Minuti di strada in testa alla giornata: dal punto in cui si trova il
  veicolo, attraverso i ritiri, fino alla zona della prima consegna.

  Va chiamata solo per la prima fascia del giorno (vedi is_first_entry_of_day).
  Zero se il veicolo non ha una posizione geocodificabile (ne' indirizzo ne'
  CAP), se non c'e' nessuna tappa da raggiungere o se il geocoder non risponde:
  e' una stima, non deve poter bloccare una prenotazione.
  """
  from .travel import front_route_minutes, get_lat_lon_for_transport

  try:
    # Il veicolo si rilegge per id, non da entry.transport: l'entry arriva spesso
    # scollegato dalla sessione (come per entry.caps, vedi query_slot_orders) e la
    # relazione lazy esploderebbe con DetachedInstanceError.
    transport = session.query(Transport).filter(Transport.id == entry.transport_id).first()
    lat, lon = get_lat_lon_for_transport(transport)
    if lat is None:
      return 0

    pickups, deliveries = _front_route_coords(orders, session, new_products=new_products, new_coord=new_coord)
    return front_route_minutes((lat, lon), pickups, deliveries)
  except requests.RequestException as error:
    logger.warning('Percorso in testa alla giornata non calcolabile (geocoder/OSRM non raggiungibile): %s', error)
    return 0


def entry_front_slot_minutes(
  entry: DeliveryCoverageEntry,
  orders: list[Order],
  pickup_minutes: int,
  session: session_type,
  new_products: dict = None,
  new_coord: tuple = None,
) -> int:
  """Quanto il lavoro in testa alla giornata (strada + sosta ai ritiri) toglie
  alla capienza della fascia.

  Nella prima fascia del giorno quel lavoro puo' cominciare prima che la fascia
  parta, dall'apertura dell'attivita': i minuti che ci stanno (entry_lead_minutes)
  non consumano la fascia, solo quelli che sforano. Con l'attivita' che apre
  alle 9 e la fascia alle 10, 39 minuti di strada e ritiri costano zero; se ne
  servissero 75, 15 finirebbero sulla fascia.

  Nelle fasce successive il veicolo e' gia' in giro: non c'e' strada in testa
  e i ritiri, se ci sono, pesano per intero sulla fascia.
  """
  if not is_first_entry_of_day(entry, session):
    return pickup_minutes

  route = entry_front_route_minutes(entry, orders, session, new_products=new_products, new_coord=new_coord)
  return max(0, route + pickup_minutes - entry_lead_minutes(entry, session))


def entry_priority_key(entry: DeliveryCoverageEntry) -> tuple:
  """Ordine di riempimento tra blocchi che si sovrappongono: si riempie prima la
  giornata del veicolo con id più basso, poi quella del successivo. Fisso e
  ripetibile, non dipende dal carico del momento."""
  return (entry.transport_id, entry.start_time, entry.id)


def _entry_fits_order(
  candidate: DeliveryCoverageEntry, assigned: list[Order], order: Order, session: session_type = None
) -> bool:
  """Se `order` sta nella capienza di `candidate` oltre agli ordini già attribuiti
  (servizi + tempo di percorso aggiunto + lavoro in testa alla giornata), con la
  stessa misura di entry_occupied_duration.

  I minuti di ritiro si contano sul gruppo intero (assegnati + nuovo ordine),
  deduplicati: se lo stesso punto di ritiro di `order` è già presente tra gli
  ordini assegnati a `candidate` non lo riconta, e concorre come chiunque altro a
  riempire prima la giornata più carica (entry_priority_key, invariato). Contarli
  sul gruppo e non solo sul nuovo ordine serve anche al margine dell'apertura,
  che si applica al totale del lavoro in testa (vedi entry_front_slot_minutes)."""
  capacity = get_entry_capacity_minutes(candidate)
  if capacity == 0:
    return True
  order_duration = calculate_order_service_duration(order)
  occupied = sum(calculate_order_service_duration(o) for o in assigned)
  travel_overhead = _travel_overhead_minutes(assigned, order.cap, new_address=order.address)
  group = assigned + [order]
  pickup_minutes = calculate_orders_pickup_minutes(group)
  front = entry_front_slot_minutes(candidate, group, pickup_minutes, session) if session is not None else pickup_minutes
  return occupied + travel_overhead + order_duration + front <= capacity


def query_entry_orders(
  entry: DeliveryCoverageEntry, dpc: date, exclude_order_id: int = None, session: session_type = None
) -> list[Order]:
  """Ordini attribuiti a `entry` nella data dpc.

  L'ordine salva solo la fascia oraria, non il veicolo: blocchi di veicoli diversi con
  la stessa fascia (start/end identici) vedono quindi gli stessi ordini. Li ripartiamo
  in modo deterministico, dal più vecchio, sul primo blocco (per entry_priority_key) che
  li copre e ha ancora spazio per il loro tempo di servizio e di percorso, così la
  giornata del primo veicolo si riempie prima di passare al successivo. Un ordine che
  non entra in nessuno resta sul primo blocco che lo copre (la scelta del cliente
  viene comunque onorata).
  """

  def _query(sess: session_type):
    siblings = (
      sess.query(DeliveryCoverageEntry)
      .options(joinedload(DeliveryCoverageEntry.caps))
      .filter(
        DeliveryCoverageEntry.day_of_week == entry.day_of_week,
        DeliveryCoverageEntry.start_time == entry.start_time,
        DeliveryCoverageEntry.end_time == entry.end_time,
      )
      .all()
    )
    if len(siblings) <= 1:
      return query_slot_orders(entry, dpc, exclude_order_id=exclude_order_id, session=sess)

    siblings.sort(key=entry_priority_key)
    covering = {}
    for sibling in siblings:
      for order in query_slot_orders(sibling, dpc, exclude_order_id=exclude_order_id, session=sess):
        covering.setdefault(order.id, (order, []))[1].append(sibling)

    assigned = {sibling.id: [] for sibling in siblings}
    for _, (order, candidates) in sorted(covering.items()):
      target = next((c for c in candidates if _entry_fits_order(c, assigned[c.id], order, session=sess)), candidates[0])
      assigned[target.id].append(order)
    return assigned[entry.id]

  if session is not None:
    return _query(session)
  with Session() as sess:
    return _query(sess)


def _entry_front_slot_for(
  entry: DeliveryCoverageEntry,
  orders: list[Order],
  pickup_minutes: int,
  session: session_type,
  new_products: dict = None,
  new_coord: tuple = None,
) -> int:
  """entry_front_slot_minutes aprendo una sessione se il chiamante non ne ha una."""
  if session is not None:
    return entry_front_slot_minutes(
      entry, orders, pickup_minutes, session, new_products=new_products, new_coord=new_coord
    )
  with Session() as sess:
    return entry_front_slot_minutes(entry, orders, pickup_minutes, sess, new_products=new_products, new_coord=new_coord)


def _travel_overhead_minutes(orders: list[Order], new_cap: str, new_address: str = None) -> int:
  """calculate_travel_overhead_minutes che degrada a zero se il geocoder non risponde.

  E' una stima del percorso aggiunto dal nuovo ordine: se Nominatim e' giu' non
  puo' far cadere la prenotazione, come non deve farla cadere la strada in testa
  alla giornata (vedi entry_front_route_minutes).
  """
  from .travel import calculate_travel_overhead_minutes

  try:
    return calculate_travel_overhead_minutes(orders, new_cap, new_address=new_address)
  except requests.RequestException as error:
    logger.warning('Sovrapprezzo di percorso non calcolabile (geocoder non raggiungibile): %s', error)
    return 0


def _new_order_coord(new_cap: str, new_address: str = None) -> tuple | None:
  """Coordinata del nuovo ordine: indirizzo se geocodificabile, altrimenti CAP.

  None se non si trova o se il geocoder non risponde: serve solo a stimare la
  strada in testa alla giornata, non deve poter bloccare la prenotazione.
  """
  try:
    lat, lon = get_lat_lon_by_address(new_address) if new_address else (None, None)
    if lat is None:
      lat, lon = get_lat_lon_by_cap(new_cap)
  except requests.RequestException as error:
    logger.warning('Geocoding del nuovo ordine non riuscito (%s): %s', new_cap, error)
    return None
  return (lat, lon) if lat is not None else None


def entry_occupied_duration(
  entry: DeliveryCoverageEntry,
  dpc: date,
  exclude_order_id: int = None,
  session: session_type = None,
  new_cap: str = None,
  new_address: str = None,
  new_products: dict = None,
) -> int:
  """Calcola il totale dei minuti occupati dagli ordini attribuiti al blocco nel giorno.

  Include la durata dei servizi di ciascun ordine, il tempo di percorso aggiuntivo
  introdotto dal nuovo ordine (new_cap, con new_address per la stima più precisa
  quando disponibile) e il lavoro in testa alla giornata: i minuti dei punti di
  ritiro richiesti dai prodotti (deduplicati, vedi calculate_orders_pickup_minutes,
  compresi quelli del nuovo ordine in new_products, payload non ancora salvato: un
  punto già coperto da un ordine esistente nella fascia non viene ricontato) e,
  nella prima fascia del giorno, la strada dal veicolo ai ritiri e verso la prima
  consegna. Di quel lavoro in testa conta solo la parte che sfora il margine
  dell'apertura dell'attività (vedi entry_front_slot_minutes).
  """
  orders = query_entry_orders(entry, dpc, exclude_order_id=exclude_order_id, session=session)
  service_minutes = sum(calculate_order_service_duration(order) for order in orders)
  pickup_minutes = calculate_orders_pickup_minutes(orders)

  if new_products:
    existing_collection_points = {cp_id for order in orders for cp_id in order_pickup_collection_point_ids(order)}
    pickup_minutes += calculate_payload_pickup_minutes(
      new_products, exclude_collection_point_ids=existing_collection_points
    )

  new_coord = None
  if new_cap:
    travel_overhead = _travel_overhead_minutes(orders, new_cap, new_address=new_address)
    new_coord = _new_order_coord(new_cap, new_address)
  else:
    travel_overhead = 0

  # Il lavoro in testa alla giornata (strada dal veicolo ai ritiri e verso la
  # prima consegna, sosta ai ritiri) pesa sulla fascia solo per la parte che non
  # sta nel margine tra l'apertura dell'attività e l'inizio della fascia.
  front = _entry_front_slot_for(entry, orders, pickup_minutes, session, new_products=new_products, new_coord=new_coord)

  return service_minutes + travel_overhead + front

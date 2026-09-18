from datetime import date
from sqlalchemy.orm import Session as session_type, joinedload

from database_api import Session
from ...database.schema import Order, Product, ServiceUser, Service, User, DeliveryCoverageEntry
from ...utils.geo import point_in_polygon
from ...utils.caps import get_lat_lon_by_address


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


def entry_occupied_duration(
  entry: DeliveryCoverageEntry,
  dpc: date,
  exclude_order_id: int = None,
  session: session_type = None,
  new_cap: str = None,
  new_address: str = None,
) -> int:
  """Calcola il totale dei minuti occupati dagli ordini nella fascia/giorno.

  Include la durata dei servizi di ciascun ordine più il tempo di percorso
  aggiuntivo introdotto dal nuovo ordine (new_cap, con new_address per la
  stima più precisa quando disponibile), se fornito.
  """
  orders = query_slot_orders(entry, dpc, exclude_order_id=exclude_order_id, session=session)
  service_minutes = sum(calculate_order_service_duration(order) for order in orders)

  if new_cap:
    from .travel import calculate_travel_overhead_minutes

    travel_overhead = calculate_travel_overhead_minutes(orders, new_cap, new_address=new_address)
  else:
    travel_overhead = 0

  return service_minutes + travel_overhead

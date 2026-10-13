from concurrent.futures import ThreadPoolExecutor
import logging
import threading
import time

import requests
from geopy.distance import geodesic

from ... import OSRM_BASE_URL
from ...database.schema import CollectionPoint, Order, Transport
from ...utils.caps import get_lat_lon_by_address, get_lat_lon_by_cap

logger = logging.getLogger(__name__)

# Velocità media urbana per fallback Haversine (km/h)
_FALLBACK_SPEED_KMH = 30.0

# Timeout per OSRM (secondi): breve, perche' una richiesta ne fa decine e con OSRM fermo ognuna
# aspetterebbe tutto il timeout (il worker gunicorn muore a 30 s).
_OSRM_TIMEOUT = 2

# Circuit breaker: dopo _BREAKER_FAILURES guasti di fila (timeout, connessione, 5xx) OSRM si considera
# fermo per _BREAKER_PAUSE secondi e le richieste vanno subito al ripiego (Haversine / ordine originale)
# invece di aspettare ciascuna il timeout. Un 200 con code diverso da Ok (nessun percorso) non e' un guasto.
_BREAKER_FAILURES = 3
_BREAKER_PAUSE = 60
_BREAKER = {'failures': 0, 'open_until': 0.0}
_BREAKER_LOCK = threading.Lock()


def _osrm_available() -> bool:
  with _BREAKER_LOCK:
    return time.monotonic() >= _BREAKER['open_until']


def _osrm_record(success: bool) -> None:
  with _BREAKER_LOCK:
    if success:
      _BREAKER['failures'] = 0
      return
    _BREAKER['failures'] += 1
    if _BREAKER['failures'] >= _BREAKER_FAILURES:
      _BREAKER['open_until'] = time.monotonic() + _BREAKER_PAUSE
      _BREAKER['failures'] = 0
      logger.warning('OSRM non risponde: ripiego senza OSRM per %s secondi', _BREAKER_PAUSE)


def _osrm_get(url: str):
  """GET verso OSRM con il circuit breaker. None se OSRM e' in pausa o non risponde."""
  if not _osrm_available():
    return None
  try:
    response = requests.get(url, timeout=_OSRM_TIMEOUT)
  except Exception as error:
    _osrm_record(False)
    logger.warning('OSRM non disponibile: %s', error)
    return None
  _osrm_record(response.status_code < 500)
  return response


# Table API per matrice durate
_OSRM_TABLE_URL = OSRM_BASE_URL + '/table/v1/driving/{coords}?annotations=duration'

# Trip API: risolve il TSP. OSRM non supporta il percorso aperto senza vincoli
# (roundtrip=false con source=any&destination=any risponde NotImplemented, anche
# sul demo pubblico), quindi si chiede il giro chiuso e lo si apre in
# trip_order_osrm togliendo il tratto piu' lungo. Il base URL e' configurabile
# via OSRM_BASE_URL, vedi src/__init__.py.
_OSRM_TRIP_URL = (
  OSRM_BASE_URL + '/trip/v1/driving/{coords}?roundtrip=true&source=any&destination=any&overview=false&steps=false'
)


# Le durate di guida tra due punti non cambiano da una richiesta all'altra:
# la stessa tratta (deposito -> primo ritiro, ultima tappa -> prima tappa della
# fascia dopo) viene chiesta per ogni giorno del calendario e per ogni ordine.
# Si memorizzano solo le risposte riuscite, un guasto non deve restare in cache.
_MATRIX_CACHE: dict[tuple, list[list[float]]] = {}
_MATRIX_CACHE_MAX = 4096


def travel_time_matrix_osrm(coords: list[tuple[float, float]]) -> list[list[float]] | None:
  """Richiede la matrice di durate di guida (secondi) via OSRM table API.

  coords: lista di (lat, lon). Ritorna la matrice N×N, o None se la chiamata fallisce.
  """
  if len(coords) < 2:
    return None
  key = tuple(coords)
  cached = _MATRIX_CACHE.get(key)
  if cached is not None:
    return cached
  # OSRM vuole lon,lat (ordine invertito rispetto a geopy)
  coords_str = ';'.join(f'{lon},{lat}' for lat, lon in coords)
  url = _OSRM_TABLE_URL.format(coords=coords_str)
  resp = _osrm_get(url)
  if resp is not None and resp.status_code == 200:
    try:
      data = resp.json()
    except ValueError:
      return None
    if data.get('code') == 'Ok':
      if len(_MATRIX_CACHE) >= _MATRIX_CACHE_MAX:
        _MATRIX_CACHE.clear()
      _MATRIX_CACHE[key] = data['durations']
      return data['durations']
  return None


def _reset_osrm_state() -> None:
  _MATRIX_CACHE.clear()
  with _BREAKER_LOCK:
    _BREAKER.update(failures=0, open_until=0.0)


# Svuota cache e circuit breaker: serve ai test, che non devono ereditare lo stato del test prima.
travel_time_matrix_osrm.cache_clear = _reset_osrm_state


def trip_order_osrm(coords: list[tuple[float, float]]) -> list[int] | None:
  """Ordine di visita ottimale per ``coords`` via OSRM Trip Service (TSP, percorso aperto).

  coords: lista di (lat, lon). Ritorna gli indici originali di ``coords`` nell'ordine di
  visita ottimale (es. [2, 0, 1] = si visita prima coords[2], poi coords[0], poi coords[1]),
  o None se la chiamata fallisce o OSRM non trova soluzione.

  OSRM restituisce un giro chiuso: lo si apre nel punto in cui il tratto tra due tappe
  consecutive e' il piu' lungo, cosi' la tappa dopo quel tratto diventa la partenza.
  """
  if len(coords) < 2:
    return None
  # OSRM vuole lon,lat (ordine invertito rispetto a geopy)
  coords_str = ';'.join(f'{lon},{lat}' for lat, lon in coords)
  url = _OSRM_TRIP_URL.format(coords=coords_str)
  resp = _osrm_get(url)
  if resp is None or resp.status_code != 200:
    return None
  try:
    data = resp.json()
    if data.get('code') == 'Ok':
      waypoints = data['waypoints']
      # waypoints[i] descrive coords[i] e porta 'waypoint_index' = sua posizione
      # nel giro ottimizzato: ordiniamo gli indici originali per quella posizione.
      cycle = sorted(range(len(waypoints)), key=lambda i: waypoints[i]['waypoint_index'])
      # legs[k] e' il tratto dalla tappa cycle[k] alla successiva (l'ultimo chiude il giro).
      legs = data['trips'][0]['legs']
      longest = max(range(len(legs)), key=lambda k: legs[k]['duration'])
      start = (longest + 1) % len(cycle)
      return cycle[start:] + cycle[:start]
  except (ValueError, KeyError, IndexError) as error:
    logger.warning('OSRM /trip: risposta non utilizzabile: %s', error)
  return None


def _haversine_travel_minutes(coords: list[tuple[float, float]]) -> int:
  """Stima fallback: somma distanze Haversine × velocità media urbana."""
  total_km = 0.0
  for i in range(len(coords) - 1):
    total_km += geodesic(coords[i], coords[i + 1]).kilometers
  return round(total_km / _FALLBACK_SPEED_KMH * 60)


def sequential_travel_minutes(coords: list[tuple[float, float]]) -> int:
  """Minuti totali del percorso sequenziale coords[0]→[1]→…→[n-1].

  Usa OSRM se disponibile, altrimenti fallback Haversine.
  """
  if len(coords) < 2:
    return 0
  matrix = travel_time_matrix_osrm(coords)
  if matrix:
    # Somma durate sequenziali dalla matrice (riga i → colonna i+1)
    total_seconds = sum(matrix[i][i + 1] for i in range(len(coords) - 1))
    return round(total_seconds / 60)
  # Fallback
  return _haversine_travel_minutes(coords)


def get_lat_lon_for_order(order: Order) -> tuple[float, float] | tuple[None, None]:
  """Coordinate dell'ordine: indirizzo completo se geocodificabile, altrimenti centroide del CAP.

  Il CAP è un fallback per quando l'indirizzo non è geocodificabile (via non
  normalizzata, indirizzo incompleto, Nominatim senza risultati), non
  un'alternativa equivalente: usarlo come prima scelta reintrodurrebbe
  l'errore di trattare come "vicini" indirizzi lontani nello stesso CAP.

  Prima di tutto la posizione salvata sull'ordine (scelta dal menu Google o
  indicata sulla mappa): e' quella vera, il geocoding resta per gli altri.
  """
  lat, lon = getattr(order, 'address_lat', None), getattr(order, 'address_lon', None)
  if lat is not None and lon is not None:
    return lat, lon
  address = getattr(order, 'address', None)
  if address:
    lat, lon = get_lat_lon_by_address(address)
    if lat is not None:
      return lat, lon
  return get_lat_lon_by_cap(getattr(order, 'cap', '') or '')


def _address_or_cap_coords(entity) -> tuple[float, float] | tuple[None, None]:
  """Indirizzo completo se geocodificabile, altrimenti centroide del CAP.

  Stesso criterio di get_lat_lon_for_order. Senza ne' indirizzo ne' CAP non si
  interroga il geocoder: una ricerca a mani vuote costerebbe comunque una
  chiamata di rete per dire che non c'e' niente.
  """
  if entity is None:
    return None, None
  address = getattr(entity, 'address', None)
  if address:
    lat, lon = get_lat_lon_by_address(address)
    if lat is not None:
      return lat, lon
  cap = getattr(entity, 'cap', None)
  if not cap:
    return None, None
  return get_lat_lon_by_cap(cap)


def get_lat_lon_for_transport(transport: Transport) -> tuple[float, float] | tuple[None, None]:
  """Punto di partenza del veicolo: il suo indirizzo, o il centroide del CAP se manca.

  Stesso criterio di get_lat_lon_for_order: l'indirizzo e' la posizione vera del
  deposito, il CAP e' il ripiego per i veicoli che l'indirizzo non ce l'hanno
  ancora (e' arrivato con la migration 066, prima c'era solo la localita').
  """
  return _address_or_cap_coords(transport)


def get_lat_lon_for_collection_point(collection_point: CollectionPoint) -> tuple[float, float] | tuple[None, None]:
  """Coordinate salvate sul punto di ritiro, altrimenti indirizzo-poi-CAP come per gli ordini."""
  lat, lon = getattr(collection_point, 'lat', None), getattr(collection_point, 'lon', None)
  if lat is not None and lon is not None:
    return lat, lon
  return _address_or_cap_coords(collection_point)


def get_lat_lon_for_orders(orders: list[Order], max_workers: int = 10) -> list[tuple[float, float] | tuple[None, None]]:
  """Risolve in parallelo le coordinate per una lista di ordini."""
  if not orders:
    return []
  workers = min(max_workers, len(orders))
  with ThreadPoolExecutor(max_workers=workers) as executor:
    return list(executor.map(get_lat_lon_for_order, orders))


def get_lat_lon_for_collection_points(
  points: list[CollectionPoint], max_workers: int = 10
) -> list[tuple[float, float] | tuple[None, None]]:
  """Risolve in parallelo le coordinate per una lista di punti di ritiro."""
  if not points:
    return []
  workers = min(max_workers, len(points))
  with ThreadPoolExecutor(max_workers=workers) as executor:
    return list(executor.map(get_lat_lon_for_collection_point, points))


def _nearest(origin: tuple[float, float], candidates: list[tuple[float, float]]) -> tuple[float, float]:
  """La candidata piu' vicina a ``origin`` in linea d'aria.

  La scelta si fa con geodesic (gratis): misurare con OSRM ogni coppia per
  decidere l'ordine costerebbe una matrice per ogni valutazione di fascia,
  dentro un ciclo che gira gia' per ognuna. La durata vera del percorso scelto
  la misura OSRM una volta sola, in front_route_minutes.
  """
  return min(candidates, key=lambda candidate: geodesic(origin, candidate).kilometers)


def front_route_minutes(
  start: tuple[float, float],
  pickups: list[tuple[float, float]],
  deliveries: list[tuple[float, float]],
) -> int:
  """Minuti del lavoro "in testa" alla giornata: dal veicolo, attraverso i punti
  di ritiro, fino alla zona della prima consegna.

  Il veicolo parte dal suo deposito, passa dai ritiri (sempre al piu' vicino
  rimasto, come li mette in fila il borderò: ritiri prima delle consegne, vedi
  schedulation/routing.py) e poi si sposta verso la consegna piu' vicina
  all'ultimo ritiro. Senza ritiri va dritto alla prima consegna. Il tratto che
  serve a *fare* i ritiri non e' qui: sono i minuti di sosta, li conta
  calculate_orders_pickup_minutes.

  Zero se non c'e' nessuna tappa da raggiungere.
  """
  path = [start]
  current = start
  remaining = list(pickups)
  while remaining:
    current = _nearest(current, remaining)
    remaining.remove(current)
    path.append(current)
  if deliveries:
    path.append(_nearest(current, list(deliveries)))
  return sequential_travel_minutes(path)


def calculate_travel_overhead_minutes(
  existing_orders: list[Order],
  new_cap: str,
  new_address: str = None,
) -> int:
  """Delta di minuti di percorso aggiunto dal nuovo ordine rispetto alla fascia esistente.

  Le coordinate usano l'indirizzo completo quando disponibile (get_lat_lon_by_address),
  con fallback al centroide del CAP: due indirizzi nello stesso CAP possono
  distare chilometri, specialmente nei CAP che coprono più comuni o zone rurali,
  e usare solo il CAP sottostimerebbe (o sovrastimerebbe) l'overhead reale.

  Calcola:
  - durata percorso sequenziale degli ordini esistenti (baseline)
  - durata percorso con il nuovo ordine aggiunto in coda
  - ritorna la differenza (overhead aggiunto dal nuovo ordine)

  Ritorna 0 se:
  - la fascia è vuota
  - il geocoding del nuovo ordine (indirizzo e CAP) fallisce
  - tutti gli ordini esistenti falliscono il geocoding
  """
  if not existing_orders or not new_cap:
    return 0

  new_lat, new_lon = (None, None)
  if new_address:
    new_lat, new_lon = get_lat_lon_by_address(new_address)
  if new_lat is None:
    new_lat, new_lon = get_lat_lon_by_cap(new_cap)
  if new_lat is None:
    logger.warning('Geocoding fallito per il nuovo ordine (indirizzo=%s, cap=%s)', new_address, new_cap)
    return 0
  new_coord = (new_lat, new_lon)

  sorted_orders = sorted(existing_orders, key=lambda o: o.id)
  existing_coords = [(lat, lon) for lat, lon in get_lat_lon_for_orders(sorted_orders) if lat is not None]

  if not existing_coords:
    # Nessun ordine esistente geocodificabile: overhead = 0 (primo ordine nella fascia)
    return 0

  with ThreadPoolExecutor(max_workers=2) as executor:
    fut_baseline = executor.submit(sequential_travel_minutes, existing_coords)
    fut_with_new = executor.submit(sequential_travel_minutes, existing_coords + [new_coord])
    baseline = fut_baseline.result()
    with_new = fut_with_new.result()

  return max(0, with_new - baseline)


def calculate_route_minutes(
  existing_orders: list[Order],
  new_cap: str = None,
  new_address: str = None,
) -> int:
  """Minuti di percorso tra gli ordini della fascia, col nuovo ordine in coda se c'e'.

  A differenza di calculate_travel_overhead_minutes non e' solo il delta: conta
  anche la strada gia' necessaria tra gli ordini esistenti, che pesa sulla
  capienza come i minuti di servizio. Il tratto dal veicolo alla prima consegna
  non e' qui (e' il lavoro in testa alla giornata, vedi front_route_minutes).

  Se il nuovo ordine non e' geocodificabile conta solo il percorso esistente.
  """
  coords = [
    (lat, lon) for lat, lon in get_lat_lon_for_orders(sorted(existing_orders, key=lambda o: o.id)) if lat is not None
  ]
  if new_cap:
    new_lat, new_lon = get_lat_lon_by_address(new_address) if new_address else (None, None)
    if new_lat is None:
      new_lat, new_lon = get_lat_lon_by_cap(new_cap)
    if new_lat is not None:
      coords.append((new_lat, new_lon))
    else:
      logger.warning('Geocoding fallito per il nuovo ordine (indirizzo=%s, cap=%s)', new_address, new_cap)
  return sequential_travel_minutes(coords)

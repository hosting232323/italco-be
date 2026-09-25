from concurrent.futures import ThreadPoolExecutor
import logging

import requests
from geopy.distance import geodesic

from ... import OSRM_BASE_URL
from ...database.schema import CollectionPoint, Order, Transport
from ...utils.caps import get_lat_lon_by_address, get_lat_lon_by_cap

logger = logging.getLogger(__name__)

# Velocità media urbana per fallback Haversine (km/h)
_FALLBACK_SPEED_KMH = 30.0

# Timeout per OSRM (secondi)
_OSRM_TIMEOUT = 5

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


def travel_time_matrix_osrm(coords: list[tuple[float, float]]) -> list[list[float]] | None:
  """Richiede la matrice di durate di guida (secondi) via OSRM table API.

  coords: lista di (lat, lon). Ritorna la matrice N×N, o None se la chiamata fallisce.
  """
  if len(coords) < 2:
    return None
  # OSRM vuole lon,lat (ordine invertito rispetto a geopy)
  coords_str = ';'.join(f'{lon},{lat}' for lat, lon in coords)
  url = _OSRM_TABLE_URL.format(coords=coords_str)
  try:
    resp = requests.get(url, timeout=_OSRM_TIMEOUT)
    if resp.status_code == 200:
      data = resp.json()
      if data.get('code') == 'Ok':
        return data['durations']
  except Exception as e:
    logger.warning('OSRM non disponibile: %s', e)
  return None


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
  try:
    resp = requests.get(url, timeout=_OSRM_TIMEOUT)
    if resp.status_code == 200:
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
  except Exception as e:
    logger.warning('OSRM /trip non disponibile: %s', e)
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
  """
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
  ancora (e' arrivato con la migration 064, prima c'era solo la localita').
  """
  return _address_or_cap_coords(transport)


def get_lat_lon_for_collection_point(collection_point: CollectionPoint) -> tuple[float, float] | tuple[None, None]:
  """Coordinate del punto di ritiro, con lo stesso indirizzo-poi-CAP degli ordini."""
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

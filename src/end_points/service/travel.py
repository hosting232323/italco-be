import logging

import requests
from geopy.distance import geodesic

from ... import OSRM_BASE_URL
from ...database.schema import Order
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

  existing_coords = []
  for order in sorted(existing_orders, key=lambda o: o.id):
    lat, lon = get_lat_lon_for_order(order)
    if lat is not None:
      existing_coords.append((lat, lon))

  if not existing_coords:
    # Nessun ordine esistente geocodificabile: overhead = 0 (primo ordine nella fascia)
    return 0

  baseline = sequential_travel_minutes(existing_coords)
  with_new = sequential_travel_minutes(existing_coords + [new_coord])
  return max(0, with_new - baseline)

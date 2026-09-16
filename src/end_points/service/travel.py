import logging

import requests
from geopy.distance import geodesic

from ...database.schema import Order
from ...utils.caps import get_lat_lon_by_cap

logger = logging.getLogger(__name__)

# Velocità media urbana per fallback Haversine (km/h)
_FALLBACK_SPEED_KMH = 30.0

# Timeout per OSRM (secondi)
_OSRM_TIMEOUT = 5

# Endpoint OSRM public (table API per matrice durate)
_OSRM_TABLE_URL = 'http://router.project-osrm.org/table/v1/driving/{coords}?annotations=duration'


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


def calculate_travel_overhead_minutes(
  existing_orders: list[Order],
  new_cap: str,
) -> int:
  """Delta di minuti di percorso aggiunto dal nuovo ordine rispetto alla fascia esistente.

  Le coordinate sono a livello di CAP (get_lat_lon_by_cap, self-hosted e cachata),
  non di indirizzo esatto: precisione sufficiente per stimare l'overhead tra
  consegne vicine, senza chiamare Nominatim/OSRM per ogni indirizzo univoco.

  Calcola:
  - durata percorso sequenziale degli ordini esistenti (baseline)
  - durata percorso con il nuovo ordine aggiunto in coda
  - ritorna la differenza (overhead aggiunto dal nuovo ordine)

  Ritorna 0 se:
  - la fascia è vuota
  - il geocoding del CAP del nuovo ordine fallisce
  - tutti i CAP esistenti falliscono il geocoding
  """
  if not existing_orders or not new_cap:
    return 0

  new_lat, new_lon = get_lat_lon_by_cap(new_cap)
  if new_lat is None:
    logger.warning('Geocoding fallito per il CAP del nuovo ordine: %s', new_cap)
    return 0
  new_coord = (new_lat, new_lon)

  existing_coords = []
  for order in sorted(existing_orders, key=lambda o: o.id):
    lat, lon = get_lat_lon_by_cap(getattr(order, 'cap', '') or '')
    if lat is not None:
      existing_coords.append((lat, lon))

  if not existing_coords:
    # Nessun ordine esistente geocodificabile: overhead = 0 (primo ordine nella fascia)
    return 0

  baseline = sequential_travel_minutes(existing_coords)
  with_new = sequential_travel_minutes(existing_coords + [new_coord])
  return max(0, with_new - baseline)

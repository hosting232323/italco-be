from functools import lru_cache

import requests

NOMINATIM_SEARCH_URL = 'https://nominatim.fastsite.it/search'
NOMINATIM_REVERSE_URL = 'https://nominatim.fastsite.it/reverse'
REQUEST_TIMEOUT = 5


def _get(url: str, **params):
  response = requests.get(
    url,
    params={**params, 'format': 'json', 'addressdetails': 1},
    headers={'User-Agent': 'italco-be'},
    timeout=REQUEST_TIMEOUT,
  )
  response.raise_for_status()
  return response.json()


def _search(**params) -> list[dict]:
  return _get(NOMINATIM_SEARCH_URL, **params, country='Italy')


def _reverse_postcode(lat: str, lon: str) -> str | None:
  return _get(NOMINATIM_REVERSE_URL, lat=lat, lon=lon).get('address', {}).get('postcode')


@lru_cache(maxsize=None)
def get_province_by_cap(cap: str) -> str:
  results = _search(postalcode=cap)
  province = results[0].get('address', {}).get('county') if results else None
  if not province:
    raise ValueError(f'CAP {cap} not found')
  return province


@lru_cache(maxsize=None)
def get_cap_by_name(city_name: str) -> str:
  results = _search(city=city_name)
  postcode = None
  if results:
    # Le città con più CAP (es. Bari) tornano come confine amministrativo senza postcode:
    # il CAP si ricava dal punto centrale restituito da Nominatim.
    postcode = results[0].get('address', {}).get('postcode') or _reverse_postcode(results[0]['lat'], results[0]['lon'])
  if not postcode:
    raise ValueError(f'City name {city_name} not found in any CAP')
  return postcode


@lru_cache(maxsize=None)
def get_lat_lon_by_cap(cap: str) -> tuple[float, float] | tuple[None, None]:
  results = _search(postalcode=cap)
  if not results:
    return None, None
  return float(results[0]['lat']), float(results[0]['lon'])


@lru_cache(maxsize=2048)
def get_lat_lon_by_address(address: str) -> tuple[float, float] | tuple[None, None]:
  """Geocodifica un indirizzo completo (via, civico, città), non il solo CAP.

  Il centroide del CAP (get_lat_lon_by_cap) è una stima grossolana: due
  indirizzi nello stesso CAP possono distare chilometri, specialmente nei CAP
  che coprono zone rurali o più comuni. Qui il risultato riflette la
  posizione reale della via.

  Cache limitata (a differenza delle funzioni sopra, che non lo sono): gli
  indirizzi hanno una cardinalità molto più alta dei CAP, una cache senza
  limite crescerebbe senza controllo su un processo long-running.
  """
  results = _search(q=address)
  if not results:
    return None, None
  return float(results[0]['lat']), float(results[0]['lon'])

import re
import logging
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Iterable

import requests

logger = logging.getLogger(__name__)

NOMINATIM_SEARCH_URL = 'https://nominatim.fastsite.it/search'
NOMINATIM_REVERSE_URL = 'https://nominatim.fastsite.it/reverse'
REQUEST_TIMEOUT = 5

# Coordinate esatte già note per un indirizzo (scelto dal menu Google nel form,
# o indicato sulla mappa): chi chiede quell'indirizzo riceve queste e non il
# geocoding Nominatim. Limitate come la cache degli indirizzi.
KNOWN_ADDRESSES_MAX = 4096
_known_addresses: OrderedDict[str, tuple[float, float]] = OrderedDict()


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
def _lookup_cap(cap: str) -> tuple[float, float] | tuple[None, None]:
  results = _search(postalcode=cap)
  if not results:
    return None, None
  return float(results[0]['lat']), float(results[0]['lon'])


def get_lat_lon_by_cap(cap: str) -> tuple[float, float] | tuple[None, None]:
  """Centroide del CAP, o (None, None) se non si trova o il geocoder non risponde.

  Un guasto di rete non e' un "non trovato": lru_cache non memorizza le
  eccezioni, quindi il lookup interno lo rilancia senza fissarlo in cache e
  qui lo si degrada. Chi geocodifica lo fa per stimare (percorso, capienza,
  ordine di visita): un geocoder giu' non deve far cadere la richiesta.
  """
  try:
    return _lookup_cap(cap)
  except requests.RequestException as error:
    logger.warning('Geocoding del CAP %s non riuscito: %s', cap, error)
    return None, None


def _address_fallback_searches(address: str) -> list[dict]:
  """Ricerche via via più larghe per un indirizzo che Nominatim non trova così com'è.

  L'indirizzo arriva dall'autocomplete Google ("Via Ludovico Ariosto, 14,
  Mesagne, BR") ma Nominatim usa i nomi di OpenStreetMap ("Via Ariosto"),
  e i civici o le sigle di provincia spesso non ci sono: prima la via senza
  civico nel comune, poi il solo comune. Ricerca strutturata e non testo
  libero: "Via Appia, Mesagne" in testo libero trova "Porta Mesagne, Via
  Appia" a Brindisi, con `city` il comune deve essere quello.
  """
  parts = [part.strip() for part in address.split(',') if part.strip()]
  if len(parts) > 1 and re.fullmatch(r'[A-Za-z]{2}', parts[-1]):
    parts = parts[:-1]
  if len(parts) < 2:
    return []

  town = parts[-1]
  street = re.sub(r'\s*\d+\s*(/\s*\w+|bis|[A-Za-z])?$', '', parts[0], flags=re.IGNORECASE).strip()
  searches = []
  if street and street.lower() != town.lower():
    searches.append({'street': street, 'city': town})
  searches.append({'city': town})
  return searches


@lru_cache(maxsize=2048)
def _lookup_address(address: str) -> tuple[float, float] | tuple[None, None]:
  for params in [{'q': address}, *_address_fallback_searches(address)]:
    results = _search(**params)
    if results:
      return float(results[0]['lat']), float(results[0]['lon'])
  return None, None


def get_lat_lon_by_address(address: str) -> tuple[float, float] | tuple[None, None]:
  """Geocodifica un indirizzo completo (via, civico, città), non il solo CAP.

  Il centroide del CAP (get_lat_lon_by_cap) è una stima grossolana: due
  indirizzi nello stesso CAP possono distare chilometri, specialmente nei CAP
  che coprono zone rurali o più comuni. Qui il risultato riflette la
  posizione reale della via. Se l'indirizzo così com'è non si trova si
  ripiega sulla via senza civico e poi sul comune (vedi
  _address_fallback_searches): una posizione approssimata vale più di
  nessuna, ad esempio per capire in quale zona di copertura cade.

  Cache limitata (a differenza dei CAP, che sono pochi): gli indirizzi hanno
  una cardinalità molto più alta, una cache senza limite crescerebbe senza
  controllo su un processo long-running. Come per il CAP, se il geocoder non
  risponde torna (None, None) e il guasto non entra in cache.

  Le coordinate registrate con remember_address_coordinates hanno la
  precedenza: sono la posizione vera, non una stima.
  """
  known = _known_addresses.get(address)
  if known:
    return known
  try:
    return _lookup_address(address)
  except requests.RequestException as error:
    logger.warning("Geocoding dell'indirizzo non riuscito: %s", error)
    return None, None


def remember_address_coordinates(address: str, lat: float, lon: float) -> None:
  """Registra la posizione esatta di un indirizzo, arrivata dal client con la richiesta.

  Da qui in poi get_lat_lon_by_address la restituisce senza geocodificare:
  copertura, capienza e strada stimata della richiesta (e delle successive
  sullo stesso indirizzo) usano tutte la stessa posizione.
  """
  if not address or lat is None or lon is None:
    return
  _known_addresses[address] = (lat, lon)
  _known_addresses.move_to_end(address)
  while len(_known_addresses) > KNOWN_ADDRESSES_MAX:
    _known_addresses.popitem(last=False)


def _clear_address_caches() -> None:
  _lookup_address.cache_clear()
  _known_addresses.clear()


get_lat_lon_by_cap.cache_clear = _lookup_cap.cache_clear
get_lat_lon_by_address.cache_clear = _clear_address_caches


def get_lat_lon_by_addresses(
  addresses: Iterable[str], max_workers: int = 10
) -> list[tuple[float, float] | tuple[None, None]]:
  """Risolve una lista di indirizzi in parallelo sfruttando la cache e ThreadPoolExecutor."""
  addr_list = list(addresses)
  if not addr_list:
    return []
  workers = min(max_workers, len(addr_list))
  with ThreadPoolExecutor(max_workers=workers) as executor:
    return list(executor.map(get_lat_lon_by_address, addr_list))


def get_lat_lon_by_caps(caps: Iterable[str], max_workers: int = 10) -> list[tuple[float, float] | tuple[None, None]]:
  """Risolve una lista di CAP in parallelo sfruttando la cache e ThreadPoolExecutor."""
  cap_list = list(caps)
  if not cap_list:
    return []
  workers = min(max_workers, len(cap_list))
  with ThreadPoolExecutor(max_workers=workers) as executor:
    return list(executor.map(get_lat_lon_by_cap, cap_list))

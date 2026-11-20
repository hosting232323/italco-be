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


# Comuni a CAP unico per cui Nominatim non da' il CAP giusto: i piccoli comuni
# hanno spesso il CAP plurimo della provincia (70010, 73020, ...) che
# OpenStreetMap non riporta, e il ripiego sul reverse geocoding restituisce il
# CAP di una via del comune vicino (Capurso -> 70019 di Triggiano, Valenzano ->
# 70129 di Bari) o nessun CAP (Casamassima, Lecce); la ricerca per nome puo'
# anche finire fuori regione (Castro -> 24063, provincia di Bergamo). Elenco
# ricavato confrontando Nominatim con i comuni pugliesi del vecchio caps.json:
# ha la precedenza su Nominatim, che altrimenti salverebbe un CAP sbagliato.
KNOWN_CITY_CAPS = {
  'acquaviva delle fonti': '70021',
  'adelfia': '70010',
  'alliste': '73040',
  'aradeo': '73040',
  'arnesano': '73010',
  'ascoli satriano': '71022',
  'bagnolo del salento': '73020',
  'binetto': '70020',
  'bitritto': '70020',
  'borgo mezzanone': '71040',
  'botrugno': '73020',
  'cannole': '73020',
  'caprarica di lecce': '73010',
  'capurso': '70010',
  'carbonara': '70131',
  'casamassima': '70010',
  'cassano delle murge': '70020',
  'castellana grotte': '70013',
  'castri di lecce': '73020',
  'castrignano del capo': '73040',
  'castro': '73030',
  'cavallino': '73020',
  'cellamare': '70010',
  'cursi': '73020',
  'cutrofiano': '73020',
  'diso': '73030',
  'erchie': '72020',
  'faggiano': '74020',
  'guagnano': '73010',
  'isole tremiti': '71040',
  'lecce': '73100',
  'leporano': '74020',
  'lizzano': '74020',
  'locorotondo': '70010',
  'lucera': '71036',
  'manfredonia': '71043',
  'martignano': '73020',
  'maruggio': '74020',
  'melissano': '73040',
  'melpignano': '73020',
  'monopoli': '70043',
  'monteiasi': '74020',
  'montemesola': '74020',
  'monteparano': '74020',
  'montesano salentino': '73030',
  'morciano di leuca': '73040',
  'neviano': '73040',
  'nociglia': '73020',
  'ortelle': '73030',
  'palmariggi': '73020',
  'poggiorsini': '70020',
  'porto cesareo': '73010',
  'roccaforzata': '74020',
  'salve': '73050',
  'san cassiano': '73020',
  'san donato di lecce': '73010',
  'san pietro in lama': '73010',
  'sannicola': '73017',
  'santa cesarea terme': '73020',
  'scorrano': '73020',
  'seclì': '73050',
  'sogliano cavour': '73010',
  'specchia': '73040',
  'statte': '74010',
  'sternatia': '73010',
  'supersano': '73040',
  'surano': '73030',
  'surbo': '73010',
  'torchiarolo': '72020',
  'toritto': '70020',
  'torricella': '74020',
  'uggiano la chiesa': '73020',
  'valenzano': '70010',
  'villa castelli': '72029',
  'zollino': '73010',
}


@lru_cache(maxsize=None)
def get_cap_by_name(city_name: str) -> str:
  known_cap = KNOWN_CITY_CAPS.get(city_name.strip().lower())
  if known_cap:
    return known_cap

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


def _address_parts(address: str) -> list[str]:
  """Le parti dell'indirizzo ("via, civico, comune"), senza la sigla di provincia finale."""
  parts = [part.strip() for part in address.split(',') if part.strip()]
  if len(parts) > 1 and re.fullmatch(r'[A-Za-z]{2}', parts[-1]):
    parts = parts[:-1]
  return parts


def _street_name(street: str) -> str:
  return re.sub(r'\s*\d+\s*(/\s*\w+|bis|[A-Za-z])?$', '', street, flags=re.IGNORECASE).strip()


def _postcode_matches(result: dict, cap: str) -> bool:
  """Se il risultato è nel CAP dato. Senza postcode nel risultato non si può dire: vale."""
  postcode = (result.get('address') or {}).get('postcode')
  return not postcode or postcode.strip() == cap.strip()


def _house_number(parts: list[str]) -> str:
  """Il civico dell'indirizzo, o '' se non c'è: attaccato alla via ("Corso Italia 12") o dopo la virgola."""
  attached = re.search(r'\s(\d+\s*(?:/\s*\w+|bis|[A-Za-z])?)$', parts[0], flags=re.IGNORECASE)
  if attached:
    return attached.group(1).strip()
  if len(parts) > 2 and re.fullmatch(r'\d+\s*(?:/\s*\w+|bis|[A-Za-z])?', parts[1], flags=re.IGNORECASE):
    return parts[1]
  return ''


def _cap_searches(address: str, cap: str) -> list[dict]:
  """Ricerche della via nel CAP dell'indirizzo: prima col civico, poi sulla sola via.

  Senza civico la posizione sarebbe quella della via e non della casa, e sulle
  vie lunghe la tappa si sposta anche di molto: la ricerca sulla sola via resta
  come ripiego, dopo la ricerca libera filtrata per CAP (vedi _lookup_address).
  Lista vuota se l'indirizzo non ha una via.
  """
  parts = _address_parts(address)
  street = _street_name(parts[0]) if len(parts) > 1 else ''
  if not street:
    return []
  postalcode = cap.strip()
  house_number = _house_number(parts)
  with_number = [{'street': f'{house_number} {street}', 'postalcode': postalcode}] if house_number else []
  return [*with_number, {'street': street, 'postalcode': postalcode}]


def _address_fallback_searches(address: str) -> list[dict]:
  """Ricerche via via più larghe per un indirizzo che Nominatim non trova così com'è.

  L'indirizzo arriva dall'autocomplete Google ("Via Ludovico Ariosto, 14,
  Mesagne, BR") ma Nominatim usa i nomi di OpenStreetMap ("Via Ariosto"),
  e i civici o le sigle di provincia spesso non ci sono: prima la via senza
  civico nel comune, poi il solo comune. Ricerca strutturata e non testo
  libero: "Via Appia, Mesagne" in testo libero trova "Porta Mesagne, Via
  Appia" a Brindisi, con `city` il comune deve essere quello.
  """
  parts = _address_parts(address)
  if len(parts) < 2:
    return []

  town = parts[-1]
  street = _street_name(parts[0])
  searches = []
  if street and street.lower() != town.lower():
    searches.append({'street': street, 'city': town})
  searches.append({'city': town})
  return searches


@lru_cache(maxsize=2048)
def _lookup_address(address: str, cap: str | None = None) -> tuple[float, float] | tuple[None, None]:
  cap_searches = _cap_searches(address, cap) if cap else []
  # Prima la via col civico nel CAP, poi la ricerca libera (filtrata per CAP), poi
  # la sola via nel CAP: la stima sulla via arriva solo se la casa non si trova.
  cap_exact, cap_street = cap_searches[:-1], cap_searches[-1:]
  for params in [*cap_exact, {'q': address}, *cap_street, *_address_fallback_searches(address)]:
    results = _search(**params)
    # La ricerca libera trova la prima via con quel nome nella provincia
    # ("Via Cesare Battisti, 742, Taranto, TA" -> Ginosa): con il CAP si scarta
    # chi cade in un altro CAP e si passa alla ricerca successiva. Solo per la
    # ricerca libera: i ripieghi sulla via o sul comune sono stime larghe, e un
    # comune con più CAP (Bari) non deve essere scartato perché ha un altro CAP.
    if cap and 'q' in params:
      results = [result for result in results if _postcode_matches(result, cap)]
    if results:
      return float(results[0]['lat']), float(results[0]['lon'])
  return None, None


def get_lat_lon_by_address(address: str, cap: str | None = None) -> tuple[float, float] | tuple[None, None]:
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

  Il CAP, quando c'è, orienta la ricerca: la stessa via esiste in molti comuni
  della provincia e senza CAP Nominatim sceglie la prima (vedi _lookup_address).
  Chi geocodifica lo stesso indirizzo deve passare lo stesso CAP, altrimenti la
  cache non viene riusata.

  Le coordinate registrate con remember_address_coordinates hanno la
  precedenza: sono la posizione vera, non una stima.
  """
  known = _known_addresses.get(address)
  if known:
    return known
  try:
    return _lookup_address(address, (cap or '').strip() or None)
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

from functools import lru_cache

import requests

NOMINATIM_SEARCH_URL = 'https://nominatim.fastsite.it/search'
REQUEST_TIMEOUT = 5


def _search(**params) -> list[dict]:
  response = requests.get(
    NOMINATIM_SEARCH_URL,
    params={**params, 'format': 'json', 'addressdetails': 1, 'country': 'Italy'},
    headers={'User-Agent': 'italco-be'},
    timeout=REQUEST_TIMEOUT,
  )
  response.raise_for_status()
  return response.json()


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
  postcode = results[0].get('address', {}).get('postcode') if results else None
  if not postcode:
    raise ValueError(f'City name {city_name} not found in any CAP')
  return postcode


@lru_cache(maxsize=None)
def get_lat_lon_by_cap(cap: str) -> tuple[float, float] | tuple[None, None]:
  results = _search(postalcode=cap)
  if not results:
    return None, None
  return float(results[0]['lat']), float(results[0]['lon'])

import json


with open('assets/caps.json', 'r') as file:
  CAPS_DATA: dict = json.load(file)


def get_province_by_cap(cap: str) -> str:
  for province, caps in CAPS_DATA.items():
    if cap in caps:
      return province

  raise ValueError(f'CAP {cap} not found in any province')


def get_cap_by_name(city_name: str) -> str | None:
  city_name_lower = city_name.lower()
  for _, caps in CAPS_DATA.items():
    for cap, info in caps.items():
      if isinstance(info, list):
        for city in info:
          if city['name'].lower() == city_name_lower:
            return cap
      else:
        if info['name'].lower() == city_name_lower:
          return cap

  raise ValueError(f'City name {city_name} not found in any CAP')


def get_cities_by_cap(cap: str) -> list[dict]:
  for province_caps in CAPS_DATA.values():
    if cap in province_caps:
      info = province_caps[cap]
      if isinstance(info, list):
        return info
      return [info]

  raise ValueError(f'CAP {cap} not found')


def get_lat_lon_by_cap(cap: str) -> tuple[float, float]:
  return [(city['lat'], city['lon']) for city in get_cities_by_cap(cap)]


def get_cap_data_by_province(province: str) -> dict:
  return CAPS_DATA[province].copy().keys() if province in CAPS_DATA else []

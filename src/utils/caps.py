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
      if info['name'].lower() == city_name_lower:
        return cap

  return None


def get_lat_lon_by_cap(cap: str) -> tuple[float, float]:
  for province in CAPS_DATA.keys():
    if cap in CAPS_DATA[province]:
      cap_data = CAPS_DATA[province][cap]
      return cap_data['lat'], cap_data['lon']

  raise ValueError('Cap not found')


def get_cap_data_by_province(province: str) -> dict:
  return CAPS_DATA[province].copy().keys() if province in CAPS_DATA else []

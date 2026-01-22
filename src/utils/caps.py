import json
from flask import request
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

from database_api import Session
from ..database.schema import Order
from ..end_points.geographic_zone import query_special_caps_by_geographic_zone, execute_query_and_format_result


with open('assets/caps.json', 'r') as file:
  CAPS_DATA: dict = json.load(file)


def check_geographic_zone() -> list[datetime]:
  province = get_province_by_cap(request.json['cap'])
  caps = CAPS_DATA[province].copy().keys() if province in CAPS_DATA else []
  for cap in query_special_caps_by_geographic_zone(province):
    if cap.type:
      caps.append(cap.code)
    else:
      caps.remove(cap.code)

  zones = execute_query_and_format_result(province)
  constraints = zones[0]['constraints'] if zones else []
  orders = get_orders_by_cap(caps)
  constraint_days = [constraint['day_of_week'] for constraint in constraints]
  start = datetime.today().date()
  allowed_dates = []
  end = start + relativedelta(months=2)
  while start <= end:
    if start.weekday() in constraint_days:
      order_count = 0
      for order in orders:
        if order.dpc == start:
          order_count += 1
      for rule in constraints:
        if rule['day_of_week'] == start.weekday() and order_count < rule['max_orders']:
          allowed_dates.append(start.strftime('%Y-%m-%d'))
          break
    start += timedelta(days=1)
  return allowed_dates


def get_province_by_cap(cap: str) -> str:
  for province, caps in CAPS_DATA.items():
    if cap in caps:
      return province
  raise ValueError(f'CAP {cap} not found in any province')


def get_cap_by_name(city_name: str) -> str | None:
  city_name_lower = city_name.lower()
  for province, caps in CAPS_DATA.items():
    for cap, info in caps.items():
      if info['name'].lower() == city_name_lower:
        return cap
  return None


def get_orders_by_cap(caps: list[str]) -> list[Order]:
  with Session() as session:
    return (
      session.query(Order)
      .filter(Order.cap.in_(caps), Order.dpc > datetime.today(), Order.dpc < datetime.today() + relativedelta(months=2))
      .all()
    )

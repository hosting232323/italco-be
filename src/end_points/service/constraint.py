from flask import request

from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from .queries import query_max_order, query_orders_in_range


def check_services_date() -> list[datetime]:
  services_id = request.json['services_id']
  services_with_max_order = query_max_order(services_id)

  start = datetime.today().date()
  allowed_dates = []
  end = start + relativedelta(months=2)
  if not services_with_max_order:
    while start <= end:
      allowed_dates.append(start.strftime('%Y-%m-%d'))
      start += timedelta(days=1)
    return allowed_dates

  min_max_services = min(
    service.max_services for service in services_with_max_order if service.max_services is not None
  )
  orders = query_orders_in_range(services_id, start, end)
  while start <= end:
    order_count = 0
    for order in orders:
      if order.dpc == start:
        order_count += 1
    if order_count < min_max_services:
      allowed_dates.append(start.strftime('%Y-%m-%d'))
    start += timedelta(days=1)
  return allowed_dates

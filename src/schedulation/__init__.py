from datetime import datetime

from ..database.enum import OrderStatus
from ..end_points.orders.queries import query_orders, format_query_result
from ..end_points.schedule.queries import get_transports_by_date
from ..end_points.transport import delivery_users_by_transport, serialize_transport

from .clustering import build_clustered_schedule_item_groups
from .assigning import assign_transports_to_schedule_items


def execute_schedulation(work_date: datetime, min_size_group: int, max_size_group: int, max_distance_km: int):
  orders = []
  work_date = work_date
  for status in [OrderStatus.BOOKED, OrderStatus.ACQUIRED]:
    for tupla in query_orders(
      [
        {'model': 'Order', 'field': 'work_date', 'value': work_date},
        {'model': 'Order', 'field': 'status', 'value': status},
      ],
    ):
      orders = format_query_result(tupla, orders)
  if len(orders) == 0:
    return {'status': 'ko', 'message': 'Ordini non trovati in questa data'}

  # Serializzati come nella pagina veicoli: la proposta mostra il mezzo con i
  # suoi corrieri, che sono quelli che faranno il borderò.
  users_by_transport = delivery_users_by_transport()
  transports = [serialize_transport(transport, users_by_transport) for transport in get_transports_by_date(work_date)]
  return {
    'status': 'ok',
    'transports': transports,
    'groups': assign_orders_to_groups(orders, transports, min_size_group, max_size_group, max_distance_km),
  }


def assign_orders_to_groups(orders, transports, min_size_group, max_size_group, max_distance_km):
  return assign_transports_to_schedule_items(
    build_clustered_schedule_item_groups(
      orders,
      min_size_group,
      max_size_group,
      max_distance_km,
    ),
    transports,
  )

from datetime import datetime

from ..database.schema import User
from ..database.enum import OrderStatus
from ..end_points.users.queries import format_user_with_info
from ..end_points.orders.queries import query_orders, format_query_result
from ..end_points.schedule.queries import get_delivery_users_by_date, get_transports_by_date

from .clustering import build_clustered_schedule_item_groups
from .assigning import assign_delivery_users_to_schedule_items


def execute_schedulation(
  user: User, work_date: datetime, min_size_group: int, max_size_group: int, max_distance_km: int
):
  orders = []
  work_date = work_date
  for status in [OrderStatus.BOOKED, OrderStatus.ACQUIRED]:
    for tupla in query_orders(
      user,
      [
        {'model': 'Order', 'field': 'work_date', 'value': work_date},
        {'model': 'Order', 'field': 'status', 'value': status},
      ],
    ):
      orders = format_query_result(tupla, orders, user)
  if len(orders) == 0:
    return {'status': 'ko', 'error': 'Ordini non trovati in questa data'}

  delivery_users = [
    format_user_with_info(delivery_user, user.role) for delivery_user in get_delivery_users_by_date(work_date)
  ]
  return {
    'status': 'ok',
    'delivery_users': delivery_users,
    'transports': [transport.to_dict() for transport in get_transports_by_date(work_date)],
    'groups': assign_orders_to_groups(orders, delivery_users, min_size_group, max_size_group, max_distance_km),
  }


def assign_orders_to_groups(orders, delivery_users, min_size_group, max_size_group, max_distance_km):
  return assign_delivery_users_to_schedule_items(
    build_clustered_schedule_item_groups(
      orders,
      min_size_group,
      max_size_group,
      max_distance_km,
    ),
    delivery_users,
  )

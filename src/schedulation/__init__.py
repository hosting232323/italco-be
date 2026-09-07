import os
from datetime import datetime

from ..database.schema import User
from ..database.enum import OrderStatus
from ..end_points.users.queries import format_user_with_info
from ..end_points.orders.queries import query_orders, format_query_result
from ..end_points.schedule.queries import get_delivery_users_by_date, get_transports_by_date

from .clustering import build_clustered_schedule_item_groups
from .clustering_rules import ClusteringContext
from .assigning import assign_delivery_users_to_schedule_items


# Strategie di pianificazione esposte da /schedule/suggestions?strategy=...
RULES_STRATEGY = 'rules'
AI_STRATEGY = 'ai'
STRATEGIES = (RULES_STRATEGY, AI_STRATEGY)


def execute_schedulation(
  user: User,
  work_date: datetime,
  min_size_group: int,
  max_size_group: int,
  max_distance_km: int,
  strategy: str = RULES_STRATEGY,
):
  if strategy not in STRATEGIES:
    return {'status': 'ko', 'message': f'Strategia di pianificazione sconosciuta: {strategy}'}
  if strategy == AI_STRATEGY and os.environ.get('AI_SCHEDULATION_ENABLED', '').lower() not in ('1', 'true', 'yes'):
    return {'status': 'ko', 'message': 'Pianificazione AI non abilitata (AI_SCHEDULATION_ENABLED)'}

  orders = []
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

  delivery_users = [
    format_user_with_info(delivery_user, user.role) for delivery_user in get_delivery_users_by_date(work_date)
  ]
  transports = [transport.to_dict() for transport in get_transports_by_date(work_date)]

  if strategy == AI_STRATEGY:
    # Import pigro: il ramo AI e' sperimentale e trascina geopy/itertools e la
    # CLI wrapper, che non servono al percorso a regole.
    from .ai import AiPlanningError, ai_execute_schedulation

    try:
      groups = ai_execute_schedulation(
        orders,
        delivery_users,
        transports,
        ClusteringContext(
          min_size_group=min_size_group,
          max_size_group=max_size_group,
          max_distance_km=max_distance_km,
        ),
      )
    except AiPlanningError as error:
      return {'status': 'ko', 'message': f'Pianificazione AI non riuscita: {error}'}
  else:
    groups = assign_orders_to_groups(orders, delivery_users, min_size_group, max_size_group, max_distance_km)

  return {
    'status': 'ok',
    'strategy': strategy,
    'delivery_users': delivery_users,
    'transports': transports,
    'groups': groups,
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

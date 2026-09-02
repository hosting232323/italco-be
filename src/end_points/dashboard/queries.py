from sqlalchemy import func, distinct, cast, Date, desc, extract
from sqlalchemy.orm import Query

from database_api import Session
from ...utils.date import handle_date
from ...database.enum import UserRole, OrderStatus
from ...database.schema import (
  Order,
  Product,
  ServiceUser,
  User,
  RaeProduct,
  RaeProductGroup,
)


TOP_CUSTOMERS_LIMIT = 8


def _filter_range(query: Query, column, start: str, end: str) -> Query:
  if start:
    query = query.filter(column >= handle_date(start))
  if end:
    query = query.filter(column <= handle_date(end))
  return query


def get_dashboard_analytics(start: str = None, end: str = None) -> dict:
  return {
    'kpis': _order_kpis(start, end),
    'orders_by_status': _orders_by_status(start, end),
    'orders_by_weekday': _orders_by_weekday(start, end),
    'orders_over_time': _orders_over_time(start, end),
    'top_customers': _top_customers(start, end),
    'rae_by_status': _rae_by_status(start, end),
    'rae_by_group': _rae_by_group(start, end),
  }


def _order_kpis(start: str, end: str) -> dict:
  with Session() as session:
    query = _filter_range(session.query(Order), Order.created_at, start, end)
    total = query.count()
    delivered = query.filter(Order.status == OrderStatus.DELIVERED).count()
    not_delivered = query.filter(Order.status == OrderStatus.NOT_DELIVERED).count()
    anomalies = query.filter(Order.anomaly.is_(True)).count()
    delays = query.filter(Order.delay.is_(True)).count()

  with Session() as session:
    rae = _filter_range(session.query(RaeProduct), RaeProduct.created_at, start, end).count()

  return {
    'total_orders': total,
    'delivered_orders': delivered,
    'not_delivered_orders': not_delivered,
    'in_progress_orders': total - delivered - not_delivered,
    'delivery_rate': round(delivered / total * 100, 1) if total else 0,
    'anomaly_orders': anomalies,
    'delay_orders': delays,
    'rae_products': rae,
  }


def _orders_by_status(start: str, end: str) -> list[dict]:
  with Session() as session:
    query = _filter_range(session.query(Order.status, func.count(Order.id)), Order.created_at, start, end).group_by(
      Order.status
    )
    return [{'label': status.value, 'count': count} for status, count in query.all()]


WEEKDAYS = ['Lun', 'Mar', 'Mer', 'Gio', 'Ven', 'Sab', 'Dom']


def _orders_by_weekday(start: str, end: str) -> list[dict]:
  delivery_date = func.coalesce(Order.booking_date, Order.dpc)
  weekday = extract('isodow', delivery_date)
  with Session() as session:
    query = _filter_range(
      session.query(weekday.label('weekday'), func.count(Order.id)), Order.created_at, start, end
    ).group_by(weekday)
    counts = {int(day): count for day, count in query.all()}
  return [{'label': WEEKDAYS[index], 'count': counts.get(index + 1, 0)} for index in range(7)]


def _orders_over_time(start: str, end: str) -> list[dict]:
  day = cast(Order.created_at, Date)
  with Session() as session:
    query = (
      _filter_range(session.query(day.label('day'), func.count(Order.id)), Order.created_at, start, end)
      .group_by(day)
      .order_by(day)
    )
    return [{'date': str(day)[:10], 'count': count} for day, count in query.all()]


def _top_customers(start: str, end: str) -> list[dict]:
  with Session() as session:
    query = (
      session.query(User.email, func.count(distinct(Order.id)).label('orders'))
      .select_from(Order)
      .join(Product, Product.order_id == Order.id)
      .join(ServiceUser, ServiceUser.id == Product.service_user_id)
      .join(User, User.id == ServiceUser.user_id)
      .filter(User.role == UserRole.CUSTOMER)
    )
    query = _filter_range(query, Order.created_at, start, end)
    query = query.group_by(User.id, User.email).order_by(desc('orders')).limit(TOP_CUSTOMERS_LIMIT)
    return [{'label': email, 'count': orders} for email, orders in query.all()]


def _rae_by_status(start: str, end: str) -> list[dict]:
  with Session() as session:
    query = _filter_range(
      session.query(RaeProduct.status, func.count(RaeProduct.id)), RaeProduct.created_at, start, end
    ).group_by(RaeProduct.status)
    return [{'label': status.value, 'count': count} for status, count in query.all()]


def _rae_by_group(start: str, end: str) -> list[dict]:
  with Session() as session:
    query = session.query(RaeProductGroup.name, func.count(RaeProduct.id).label('quantity')).join(
      RaeProduct, RaeProduct.rae_product_group_id == RaeProductGroup.id
    )
    query = _filter_range(query, RaeProduct.created_at, start, end)
    query = query.group_by(RaeProductGroup.id, RaeProductGroup.name).order_by(desc('quantity'))
    return [{'label': name, 'count': quantity} for name, quantity in query.all()]

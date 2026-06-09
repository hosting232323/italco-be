from datetime import date
from sqlalchemy.orm import Session as session_type
from sqlalchemy import extract, func, and_, cast, Date, desc

from ...utils.date import handle_date
from ...utils.query import limit_per_entity
from ...database.enum import RaeStatus
from database_api.operations import db_session_decorator
from ...database.schema import (
  Order,
  Product,
  RaeProduct,
  RaeProductGroup,
  User,
  Schedule,
  ScheduleItem,
  ScheduleItemOrder,
)


@db_session_decorator(commit=False)
def query_rae_products(
  filters: list[dict], limit: int = None, session: session_type = None
) -> list[tuple[RaeProduct, RaeProductGroup, User, Order, Schedule]]:
  query = (
    session.query(RaeProduct, RaeProductGroup, User, Order, Schedule)
    .join(RaeProductGroup, RaeProduct.rae_product_group_id == RaeProductGroup.id)
    .join(User, RaeProduct.user_id == User.id)
    .join(Order, RaeProduct.order_id == Order.id)
    .outerjoin(ScheduleItemOrder, ScheduleItemOrder.order_id == Order.id)
    .outerjoin(ScheduleItem, ScheduleItem.id == ScheduleItemOrder.schedule_item_id)
    .outerjoin(Schedule, Schedule.id == ScheduleItem.schedule_id)
  )

  for filter in filters:
    model = globals()[filter['model']]
    field = getattr(model, filter['field'])
    value = filter['value']

    if field in [Schedule.date, RaeProduct.created_at, RaeProduct.emission_date] and type(value) is list:
      query = query.filter(field >= handle_date(value[0]), field <= handle_date(value[1]))
    elif field in [RaeProduct.created_at, RaeProduct.emission_date]:
      query = query.filter(cast(field, Date) == value)
    elif field == RaeProduct.status:
      query = query.filter(field == RaeStatus(value))
    elif isinstance(value, list):
      query = query.filter(field.in_(value))
    else:
      query = query.filter(field == value)

  return limit_per_entity(
    query.order_by(desc(Schedule.date), desc(RaeProduct.emission_date)),
    RaeProduct.id,
    limit,
    subquery_order_by=(desc(func.max(Schedule.date)), desc(RaeProduct.emission_date)),
  ).all()


@db_session_decorator(commit=False)
def query_count_rae_products(user_id: int, session: session_type = None) -> int:
  return (
    session.query(func.count(RaeProduct.id))
    .filter(
      RaeProduct.status != RaeStatus.GENERATED,
      RaeProduct.user_id == user_id,
      extract('year', RaeProduct.emission_date) == date.today().year,
    )
    .scalar()
  )


@db_session_decorator(commit=False)
def get_product_and_group(rae_product_id: int, session: session_type = None) -> dict:
  result: tuple[RaeProduct, RaeProductGroup] = (
    session.query(RaeProduct, RaeProductGroup)
    .join(RaeProductGroup, and_(RaeProduct.rae_product_group_id == RaeProductGroup.id, RaeProduct.id == rae_product_id))
    .first()
  )

  rae_product = result[0].to_dict()
  rae_product['name'] = result[1].name
  rae_product['cer_code'] = result[1].cer_code
  rae_product['group_code'] = result[1].group_code
  return rae_product


@db_session_decorator()
def get_rae_products_by_order(order: Order, session: session_type = None) -> list[RaeProduct]:
  return (
    session.query(RaeProduct)
    .join(Product, and_(Product.rae_product_id == RaeProduct.id, Product.order_id == order.id))
    .all()
  )


@db_session_decorator(commit=False)
def get_rae_product_tuples_by_order(order: Order, session: session_type = None) -> list[tuple[RaeProduct, Product]]:
  return (
    session.query(RaeProduct, Product)
    .join(Product, and_(Product.rae_product_id == RaeProduct.id, Product.order_id == order.id))
    .all()
  )

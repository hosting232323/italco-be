from datetime import date, datetime
from sqlalchemy import extract, func, and_, exists, cast, Date, desc

from database_api import Session
from ...utils.date import handle_date
from ...database.enum import RaeStatus
from ..users.queries import format_user_with_info
from database_api.operations import update, delete, get_by_id
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


def get_rae_products(user: User, filters: list[dict]):
  rae_products = []
  for tupla in query_rae_products(filters):
    rae_products = format_query_result(tupla, rae_products, user)
  return {'status': 'ok', 'rae_products': rae_products}


def update_rae_product(id: int, data: dict):
  update(
    get_by_id(RaeProduct, id),
    {'status': RaeStatus(data['status']), **({'link': data['link']} if 'link' in data else {})},
  )
  return {'status': 'ok', 'message': 'Operazione completata'}


def delete_rae_product(id: int):
  if check_orders(id):
    return {'status': 'ko', 'message': 'Prodotto Rae ancora associato ad un Ordine'}

  delete(get_by_id(RaeProduct, id))
  return {'status': 'ok', 'message': 'Operazione completata'}


def query_rae_products(filters: list[dict]) -> list[tuple[RaeProduct, RaeProductGroup, User, Order, Schedule]]:
  with Session() as session:
    query = (
      session.query(RaeProduct, RaeProductGroup, User, Order, Schedule)
      .join(RaeProductGroup, RaeProduct.rae_product_group_id == RaeProductGroup.id)
      .join(User, RaeProduct.user_id == User.id)
      .outerjoin(Product, RaeProduct.id == Product.rae_product_id)
      .outerjoin(Order, Product.order_id == Order.id)
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
      else:
        query = query.filter(field == value)
    return query.order_by(desc(Schedule.date)).all()


def format_query_result(tupla: tuple[RaeProduct, RaeProductGroup, User, Order, Schedule], list: list[dict], user: User):
  for element in list:
    if element['id'] == tupla[0].id:
      return list

  output = {
    **tupla[0].to_dict(),
    'product_group': tupla[1].to_dict(),
    'user': format_user_with_info(tupla[2], user.role),
    'rae_number': query_count_rae_products(tupla[0].emission_date, tupla[2].id)
    if tupla[0].status != RaeStatus.GENERATED and tupla[0].emission_date
    else None,
  }
  if tupla[3]:
    output['order'] = tupla[3].to_dict()
  if tupla[4]:
    output['schedule'] = tupla[4].to_dict()
  list.append(output)
  return list


def check_orders(rae_product_id) -> bool:
  with Session() as session:
    return session.query(exists().where(Product.rae_product_id == rae_product_id)).scalar()


def query_count_rae_products(emission_date: datetime, user_id: int) -> int:
  with Session() as session:
    return (
      session.query(func.count(RaeProduct.id))
      .filter(
        RaeProduct.status != RaeStatus.GENERATED,
        RaeProduct.user_id == user_id,
        extract('year', RaeProduct.emission_date) == date.today().year,
        RaeProduct.emission_date <= emission_date,
      )
      .scalar()
    )


def get_product_and_group(rae_product_id: int) -> dict:
  with Session() as session:
    result: tuple[RaeProduct, RaeProductGroup] = (
      session.query(RaeProduct, RaeProductGroup)
      .join(
        RaeProductGroup, and_(RaeProduct.rae_product_group_id == RaeProductGroup.id, RaeProduct.id == rae_product_id)
      )
      .first()
    )

    rae_product = result[0].to_dict()
    rae_product['name'] = result[1].name
    rae_product['cer_code'] = result[1].cer_code
    rae_product['group_code'] = result[1].group_code
    return rae_product


def get_rae_products_by_order(order: Order) -> list[RaeProduct]:
  with Session() as session:
    return (
      session.query(RaeProduct)
      .join(Product, and_(Product.rae_product_id == RaeProduct.id, Product.order_id == order.id))
      .all()
    )


def emit_rae_products(order: Order, session):
  for rae_product in get_rae_products_by_order(order):
    update(rae_product, {'status': RaeStatus.EMITTED, 'emission_date': datetime.now()}, session=session)


def get_rae_product_tuples_by_order(order: Order) -> list[tuple[RaeProduct, Product]]:
  with Session() as session:
    return (
      session.query(RaeProduct, Product)
      .join(Product, and_(Product.rae_product_id == RaeProduct.id, Product.order_id == order.id))
      .all()
    )

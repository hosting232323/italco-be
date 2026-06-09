from datetime import date, datetime
from sqlalchemy import extract, func, and_, exists, cast, Date, desc

from database_api import Session
from ...utils.date import handle_date
from ...database.enum import RaeStatus
from ..users.queries import format_user_with_info
from database_api.operations import update, get_by_id, create, db_session_decorator
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


def create_rae_product(
  quantity: int, rae_product_group_id: int, order_id: int, user_id: int, session, schedule_item: ScheduleItem = None
) -> RaeProduct:
  body = {
    'number': 0,
    'user_id': user_id,
    'order_id': order_id,
    'quantity': quantity,
    'status': RaeStatus.GENERATED,
    'rae_product_group_id': rae_product_group_id,
  }

  if schedule_item:
    body['emission_date'] = datetime.now()
    body['status'] = RaeStatus.EMITTED
    body['number'] = query_count_rae_products(user_id, session=session) + 1

  return create(RaeProduct, body, session=session)


def update_rae_product(id: int, data: dict):
  update(
    get_by_id(RaeProduct, id),
    {'status': RaeStatus(data['status']), 'link': data['link']},
  )
  return {'status': 'ok', 'message': 'Operazione completata'}


@db_session_decorator()
def query_rae_products(
  filters: list[dict], session: Session = None
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
    else:
      query = query.filter(field == value)
  return query.order_by(desc(Schedule.date), desc(RaeProduct.emission_date)).all()


def format_query_result(tupla: tuple[RaeProduct, RaeProductGroup, User, Order, Schedule], list: list[dict], user: User):
  for element in list:
    if element['id'] == tupla[0].id:
      return list

  output = {
    **tupla[0].to_dict(),
    'order': tupla[3].to_dict(),
    'product_group': tupla[1].to_dict(),
    'user': format_user_with_info(tupla[2], user.role),
  }
  if tupla[4]:
    output['schedule'] = tupla[4].to_dict()
  list.append(output)
  return list


@db_session_decorator()
def check_orders(rae_product_id: int, session: Session = None) -> bool:
  return session.query(exists().where(Product.rae_product_id == rae_product_id)).scalar()


@db_session_decorator()
def query_count_rae_products(user_id: int, session: Session = None) -> int:
  return (
    session.query(func.count(RaeProduct.id))
    .filter(
      RaeProduct.status != RaeStatus.GENERATED,
      RaeProduct.user_id == user_id,
      extract('year', RaeProduct.emission_date) == date.today().year,
    )
    .scalar()
  )


@db_session_decorator()
def get_product_and_group(rae_product_id: int, session: Session = None) -> dict:
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
def get_rae_products_by_order(order: Order, session: Session = None) -> list[RaeProduct]:
  return (
    session.query(RaeProduct)
    .join(Product, and_(Product.rae_product_id == RaeProduct.id, Product.order_id == order.id))
    .all()
  )


def emit_rae_products(order: Order, session):
  for rae_product in get_rae_products_by_order(order, session=session):
    update(
      rae_product,
      {
        'status': RaeStatus.EMITTED,
        'emission_date': datetime.now(),
        'number': query_count_rae_products(rae_product.user_id, session=session) + 1,
      },
      session=session,
    )


def recreate_rae_products(order: Order, session):
  rae_product_ids = {}
  for tupla in get_rae_product_tuples_by_order(order, session=session):
    if tupla[0].id not in rae_product_ids:
      rae_product_ids[tupla[0].id] = create_rae_product(
        tupla[0].quantity, tupla[0].rae_product_group_id, order.id, tupla[0].user_id, session=session
      ).id
      update(tupla[0], {'status': RaeStatus.ANNULLED}, session=session)
    update(tupla[1], {'rae_product_id': rae_product_ids[tupla[0].id]}, session=session)


@db_session_decorator()
def get_rae_product_tuples_by_order(order: Order, session: Session = None) -> list[tuple[RaeProduct, Product]]:
  return (
    session.query(RaeProduct, Product)
    .join(Product, and_(Product.rae_product_id == RaeProduct.id, Product.order_id == order.id))
    .all()
  )

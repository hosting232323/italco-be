from datetime import datetime

from ...database.enum import RaeStatus
from ..users.queries import format_user_with_info
from database_api.operations import update, get_by_id, create
from .queries import (
  query_rae_products,
  query_count_rae_products,
  get_rae_products_by_order,
  get_rae_product_tuples_by_order,
)
from ...database.schema import (
  Order,
  RaeProduct,
  RaeProductGroup,
  User,
  Schedule,
)


def get_rae_products(user: User, filters: list[dict]):
  rae_products = []
  for tupla in query_rae_products(filters, 500):
    rae_products = format_query_result(tupla, rae_products, user)
  return {'status': 'ok', 'rae_products': rae_products}


def create_rae_product(
  quantity: int, rae_product_group_id: int, order_id: int, user_id: int, session, schedule: Schedule = None
) -> RaeProduct:
  body = {
    'number': 0,
    'user_id': user_id,
    'order_id': order_id,
    'quantity': quantity,
    'status': RaeStatus.GENERATED,
    'rae_product_group_id': rae_product_group_id,
  }

  if schedule:
    body['emission_date'] = datetime.now()
    body['dtr_date'] = schedule.date
    body['status'] = RaeStatus.EMITTED
    body['number'] = query_count_rae_products(user_id, session=session) + 1

  return create(RaeProduct, body, session=session)


def update_rae_product(id: int, data: dict):
  update(
    get_by_id(RaeProduct, id),
    {'status': RaeStatus(data['status']), 'link': data['link']},
  )
  return {'status': 'ok', 'message': 'Operazione completata'}


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


def emit_rae_products(order: Order, schedule: Schedule, session):
  for rae_product in get_rae_products_by_order(order, session=session):
    update(
      rae_product,
      {
        'status': RaeStatus.EMITTED,
        'emission_date': datetime.now(),
        'dtr_date': schedule.date,
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

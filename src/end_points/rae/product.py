from datetime import date
from sqlalchemy import extract, func, and_

from database_api import Session
from ...database.enum import RaeStatus
from database_api.operations import create, update
from ...database.schema import Order, Product, RaeProduct, RaeProductGroup


def get_rae_products():
  return {
    'status': 'ok',
    'rae_products': [rae_product.to_dict() for rae_product in query_rae_products()],
  }


def query_rae_products() -> list[RaeProduct]:
  with Session() as session:
    return session.query(RaeProduct).all()


def query_count_rae_products(rae_product_id: int, user_id: int) -> int:
  with Session() as session:
    return (
      session.query(func.count(RaeProduct.id))
      .filter(
        RaeProduct.id <= rae_product_id,
        RaeProduct.user_id == user_id,
        extract('year', RaeProduct.created_at) == date.today().year,
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


def recreate_rae_products(order: Order, session):
  rae_product_ids = {}
  for tupla in get_rae_product_tuples_by_order(order):
    if tupla[0].id not in rae_product_ids:
      rae_product_ids[tupla[0].id] = create(
        RaeProduct,
        {
          'user_id': tupla[0].user_id,
          'quantity': tupla[0].quantity,
          'rae_product_group_id': tupla[0].rae_product_group_id,
        },
        session=session,
      ).id
      update(tupla[0], {'status': RaeStatus.ANNULLED})
    update(tupla[1], {'rae_product_id': rae_product_ids[tupla[0].id]}, session=session)


def get_rae_product_tuples_by_order(order: Order) -> list[tuple[RaeProduct, Product]]:
  with Session() as session:
    return (
      session.query(RaeProduct, Product)
      .join(Product, and_(Product.rae_product_id == RaeProduct.id, Product.order_id == order.id))
      .all()
    )

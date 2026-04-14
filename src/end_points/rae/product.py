from datetime import date
from sqlalchemy import extract, func, and_

from database_api import Session
from database_api.operations import get_by_id
from ...database.schema import Product, ServiceUser, RaeProduct, RaeProductGroup


def get_rae_products():
  return {
    'status': 'ok',
    'rae_products': [rae_product.to_dict() for rae_product in query_rae_products()],
  }


def query_rae_products() -> list[RaeProduct]:
  with Session() as session:
    return session.query(RaeProduct).all()


def query_count_rae_products(rae_product_id: int, user_id: int) -> int:
  rae_product: Product = get_by_id(RaeProduct, rae_product_id)
  if not rae_product:
    return 0

  with Session() as session:
    return (
      session.query(func.coalesce(func.sum(1 + func.coalesce(RaeProduct.cancellations, 0)), 0))
      .join(
        Product,
        and_(
          Product.rae_product_id == RaeProduct.id,
          RaeProduct.id <= rae_product_id,
          extract('year', RaeProduct.created_at) == date.today().year,
        ),
      )
      .join(
        ServiceUser,
        and_(ServiceUser.id == Product.service_user_id, ServiceUser.user_id == user_id),
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

from database_api import Session
from database_api.operations import create, update as database_update
import pytest

from src.database.enum import RaeStatus
from src.database.schema import (
  Carrier,
  CollectionCenter,
  Disposal,
  Order,
  RaeProduct,
  RaeProductGroup,
  User,
)
from src.end_points.rae import disposal as disposal_module


def test_create_disposal_rolls_back_all_changes_on_product_failure(seeded_db, monkeypatch):
  code = 'atomic-rae-disposal'
  with Session() as session:
    carrier = create(Carrier, {'company_name': 'Carrier'}, session=session)
    center = create(CollectionCenter, {'company_name': 'Center'}, session=session)
    user_id = session.query(User.id).first()[0]
    order_id = session.query(Order.id).first()[0]
    group_id = session.query(RaeProductGroup.id).first()[0]
    products = [
      create(
        RaeProduct,
        {
          'user_id': user_id,
          'order_id': order_id,
          'rae_product_group_id': group_id,
          'status': RaeStatus.GENERATED,
        },
        session=session,
      )
      for _ in range(2)
    ]
    product_ids = [product.id for product in products]
    carrier_id = carrier.id
    center_id = center.id
    session.commit()

  update_calls = 0

  def update_then_fail(entity, data, session=None):
    nonlocal update_calls
    update_calls += 1
    if update_calls == 2:
      raise RuntimeError('second product failed')
    return database_update(entity, data, session=session)

  monkeypatch.setattr(disposal_module, 'update', update_then_fail)
  payload = {
    'code': code,
    'carrier_id': carrier_id,
    'collection_center_id': center_id,
    'rae_product_ids': product_ids,
  }

  with pytest.raises(RuntimeError, match='second product failed'):
    disposal_module.create_rae_disposal(payload)

  with Session() as session:
    assert session.query(Disposal).filter(Disposal.code == code).count() == 0
    reloaded_products = session.query(RaeProduct).filter(RaeProduct.id.in_(product_ids)).all()
    assert all(product.disposal_id is None for product in reloaded_products)
    assert all(product.status == RaeStatus.GENERATED for product in reloaded_products)

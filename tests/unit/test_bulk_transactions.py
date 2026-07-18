from types import SimpleNamespace

from database_api import Session
from database_api.operations import create, delete as database_delete, update as database_update
from flask import Flask
import pytest

from src.database.schema import CustomerRule, Order, Product, ServiceUser, User
from src.end_points import customer_rule as customer_rule_module
from src.end_points.orders import crud as order_crud_module


def test_customer_rule_bulk_delete_rolls_back_on_second_failure(seeded_db, monkeypatch):
  app = Flask(__name__)
  with Session() as session:
    rule_ids = [rule.id for rule in session.query(CustomerRule).limit(2).all()]

  delete_calls = 0

  def delete_then_fail(entity, session=None):
    nonlocal delete_calls
    delete_calls += 1
    if delete_calls == 2:
      raise RuntimeError('second delete failed')
    return database_delete(entity, session=session)

  monkeypatch.setattr(customer_rule_module, 'delete', delete_then_fail)
  with app.test_request_context('/customer-rules', method='DELETE', json={'ids': rule_ids}):
    with pytest.raises(RuntimeError, match='second delete failed'):
      customer_rule_module.delete_customer_rules.__wrapped__(SimpleNamespace())

  with Session() as session:
    assert session.query(CustomerRule).filter(CustomerRule.id.in_(rule_ids)).count() == 2


def test_order_customer_bulk_update_rolls_back_on_second_failure(seeded_db, monkeypatch):
  with Session() as session:
    original_product = session.query(Product).first()
    order: Order = original_product.order
    old_service_user: ServiceUser = original_product.service_user
    target_user_id = session.query(User.id).filter(User.id != old_service_user.user_id).first()[0]
    target_service_user = create(
      ServiceUser,
      {
        'user_id': target_user_id,
        'service_id': old_service_user.service_id,
        'price': old_service_user.price,
      },
      session=session,
    )
    second_product = create(
      Product,
      {
        'name': 'second bulk product',
        'order_id': order.id,
        'service_user_id': old_service_user.id,
      },
      session=session,
    )
    product_ids = [original_product.id, second_product.id]
    old_service_user_id = old_service_user.id
    order_id = order.id
    session.commit()

  update_calls = 0

  def update_then_fail(entity, data, session=None):
    nonlocal update_calls
    update_calls += 1
    if update_calls == 2:
      raise RuntimeError('second update failed')
    return database_update(entity, data, session=session)

  monkeypatch.setattr(order_crud_module, 'update', update_then_fail)
  with pytest.raises(RuntimeError, match='second update failed'):
    order_crud_module.update_order_customer(SimpleNamespace(), target_user_id, order_id)

  with Session() as session:
    reloaded = session.query(Product).filter(Product.id.in_(product_ids)).all()
    assert all(product.service_user_id == old_service_user_id for product in reloaded)
    assert target_service_user.id is not None

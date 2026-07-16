import pytest
from sqlalchemy.exc import IntegrityError

from database_api import Session
from database_api.operations import create, delete

from src.database.enum import OrderStatus, UserRole
from src.database.schema import (
  DtrDocument,
  FirFirstDocument,
  FirFourthDocument,
  Motivation,
  Product,
  User,
)

from tests.unit.factories import (
  create_order,
  create_product,
  create_service,
  create_service_user,
  create_user,
)


def test_format_user_full_dict_for_admin_viewer(db):
  user = create_user(UserRole.CUSTOMER, nickname='cliente-1', password='segreta')

  formatted = user.format_user(UserRole.ADMIN)

  assert formatted['nickname'] == 'cliente-1'
  assert formatted['password'] == 'segreta'
  assert formatted['role'] == 'Customer'


def test_format_user_minimal_dict_for_other_viewers(db):
  user = create_user(UserRole.CUSTOMER, nickname='cliente-2', password='segreta')

  formatted = user.format_user(UserRole.DELIVERY)

  assert formatted == {'id': user.id, 'nickname': 'cliente-2', 'role': 'Customer'}
  assert 'password' not in formatted


def test_nickname_must_be_unique(db):
  create_user(UserRole.DELIVERY, nickname='doppione')

  with pytest.raises(IntegrityError):
    create_user(UserRole.DELIVERY, nickname='doppione')


def test_order_defaults(db):
  order = create_order()

  assert order.status == OrderStatus.ACQUIRED
  assert order.version == 0
  assert order.anomaly is False or order.anomaly is None
  assert order.confirmed is False or order.confirmed is None


def test_order_cascade_deletes_children(db):
  customer = create_user(UserRole.CUSTOMER)
  service = create_service()
  service_user = create_service_user(customer, service)
  order = create_order()
  product = create_product(order, service_user)
  motivation = create(
    Motivation, {'order_id': order.id, 'status': OrderStatus.NOT_DELIVERED, 'text': 'assente'}
  )

  delete(order)

  with Session() as session:
    assert session.query(Product).filter_by(id=product.id).count() == 0
    assert session.query(Motivation).filter_by(id=motivation.id).count() == 0


def test_user_cascade_deletes_service_links(db):
  customer = create_user(UserRole.CUSTOMER)
  service = create_service()
  create_service_user(customer, service)

  delete(customer)

  with Session() as session:
    assert session.query(User).filter_by(id=customer.id).count() == 0


def test_document_tables_and_constraints():
  assert DtrDocument.__tablename__ == 'dtr_document'
  assert FirFirstDocument.__tablename__ == 'fir_first_document'
  assert FirFourthDocument.__tablename__ == 'fir_fourth_document'
  assert FirFirstDocument.__table__.c.disposal_id.nullable is False
  assert FirFourthDocument.__table__.c.disposal_id.nullable is False
  assert FirFirstDocument.__table__.c.disposal_id.unique is True
  assert FirFourthDocument.__table__.c.disposal_id.unique is True


def test_to_dict_serializes_enum_and_dates(db):
  order = create_order(status=OrderStatus.BOOKED)

  as_dict = order.to_dict()

  assert as_dict['status'] == 'Booked'
  assert as_dict['dpc'] == order.dpc.strftime('%Y-%m-%d')
  assert '_sa_instance_state' not in as_dict

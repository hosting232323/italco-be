from database_api import Session

from src.database.seed import can_create, seed_data
from src.database.enum import UserRole
from src.database.schema import (
  CollectionPoint,
  Constraint,
  CustomerRule,
  GeographicZone,
  Motivation,
  Order,
  Photo,
  Product,
  RaeProductGroup,
  Schedule,
  Service,
  Transport,
  User,
)


def test_can_create_is_true_on_empty_database(db):
  assert can_create() is True


def test_seed_data_populates_all_domains(db):
  seed_data()

  with Session() as session:
    users = session.query(User).all()
    roles = {user.role for user in users}
    assert {UserRole.ADMIN, UserRole.OPERATOR, UserRole.DELIVERY, UserRole.CUSTOMER} == roles
    assert session.query(User).filter(User.nickname == 'admin').count() == 1

    assert session.query(Transport).count() == 10
    assert session.query(CollectionPoint).count() == 10
    assert session.query(Schedule).count() == 10
    assert session.query(RaeProductGroup).count() == 10
    assert session.query(GeographicZone).count() == 10
    assert session.query(Constraint).count() == 10
    assert session.query(CustomerRule).count() >= 10
    assert session.query(Order).count() == 20
    assert session.query(Product).count() == 20
    assert session.query(Photo).count() == 10
    assert session.query(Motivation).count() == 10

    # 3 servizi professional + 10 standard
    assert session.query(Service).filter(Service.professional.is_(True)).count() == 3
    assert session.query(Service).filter(Service.professional.is_(False)).count() == 10

    # Le password del seed sono cifrate, mai in chiaro
    admin = session.query(User).filter(User.nickname == 'admin').one()
    assert admin.password != '1234admin'


def test_seed_data_is_idempotent(db):
  seed_data()
  with Session() as session:
    users_after_first_run = session.query(User).count()

  seed_data()

  with Session() as session:
    assert session.query(User).count() == users_after_first_run


def test_can_create_is_false_after_seeding(db):
  seed_data()

  assert can_create() is False

from sqlalchemy import asc, desc

from database_api import Session
from src.database.enum import UserRole
from src.database.schema import User
from src.utils.query import limit_per_entity

from tests.unit.factories import create_user


def _query_users(session):
  return session.query(User).order_by(desc(User.id))


def test_limit_per_entity_limits_distinct_entities(db):
  users = [create_user(UserRole.DELIVERY) for _ in range(5)]

  with Session() as session:
    results = limit_per_entity(_query_users(session), User.id, 3).all()

  assert len(results) == 3
  assert {user.id for user in results} <= {user.id for user in users}


def test_limit_per_entity_with_none_limit_returns_all(db):
  for _ in range(4):
    create_user(UserRole.DELIVERY)

  with Session() as session:
    results = limit_per_entity(_query_users(session), User.id, None).all()

  assert len(results) == 4


def test_limit_per_entity_with_subquery_order_by(db):
  users = [create_user(UserRole.DELIVERY) for _ in range(4)]

  with Session() as session:
    results = limit_per_entity(
      _query_users(session), User.id, 2, subquery_order_by=(asc(User.id),)
    ).all()

  # L'ordinamento del sottoquery seleziona i primi due id creati
  assert {user.id for user in results} == {users[0].id, users[1].id}

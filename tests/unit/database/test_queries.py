from src.database.queries import get_user_by_nickname
from src.database.enum import UserRole

from tests.unit.factories import create_user


def test_get_user_by_nickname_returns_matching_user(db):
  user = create_user(UserRole.OPERATOR, nickname='operatore-x')

  found = get_user_by_nickname('operatore-x')

  assert found is not None
  assert found.id == user.id
  assert found.role == UserRole.OPERATOR


def test_get_user_by_nickname_returns_none_for_unknown(db):
  create_user(UserRole.OPERATOR, nickname='esiste')

  assert get_user_by_nickname('non-esiste') is None

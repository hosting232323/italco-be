from src.database.queries import get_user_by_email
from src.database.enum import UserRole

from tests.unit.factories import create_user


def test_get_user_by_email_returns_matching_user(db):
  user = create_user(UserRole.OPERATOR, email='operatore-x')

  found = get_user_by_email('operatore-x')

  assert found is not None
  assert found.id == user.id
  assert found.role == UserRole.OPERATOR


def test_get_user_by_email_returns_none_for_unknown(db):
  create_user(UserRole.OPERATOR, email='esiste')

  assert get_user_by_email('non-esiste') is None

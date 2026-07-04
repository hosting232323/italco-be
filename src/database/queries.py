from database_api import Session

from .schema import User


def get_user_by_nickname(nickname: str) -> User | None:
  with Session() as session:
    return session.query(User).filter(User.nickname == nickname).first()

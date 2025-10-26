from database_api import Session
from ...database.enum import UserRole
from ...database.schema import User, ServiceUser, CollectionPoint, CustomerRule, OrderServiceUser


def query_users(user: User, role: UserRole = None) -> list[User]:
  with Session() as session:
    query = session.query(User)
    if user.role == UserRole.DELIVERY:
      query = query.filter(User.role == UserRole.CUSTOMER)
    if user.role == UserRole.OPERATOR:
      query = query.filter(User.role.in_([UserRole.CUSTOMER, UserRole.DELIVERY]))

    if role:
      query = query.filter(User.role == role)
    return query.all()


def count_user_dependencies(id: int) -> dict:
  with Session() as session:
    return {
      'serviceUsers': session.query(ServiceUser).filter(ServiceUser.user_id == id).count(),
      'customerRules': session.query(CustomerRule).filter(CustomerRule.user_id == id).count(),
      'collectionPoints': session.query(CollectionPoint).filter(CollectionPoint.user_id == id).count(),
      'blockedOrders': (
        session.query(OrderServiceUser)
        .join(ServiceUser, ServiceUser.id == OrderServiceUser.service_user_id)
        .filter(ServiceUser.user_id == id)
        .count()
      ),
    }


def get_user_by_nickname(nickname: str) -> User | None:
  with Session() as session:
    return session.query(User).filter(User.nickname == nickname).first()

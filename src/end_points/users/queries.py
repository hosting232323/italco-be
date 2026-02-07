from sqlalchemy import and_

from database_api import Session
from ...database.enum import UserRole
from ...database.schema import (
  User,
  ServiceUser,
  CollectionPoint,
  CustomerRule,
  Product,
  DeliveryUserInfo,
  CustomerUserInfo,
)


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
        session.query(Product)
        .join(ServiceUser, ServiceUser.id == Product.service_user_id)
        .filter(ServiceUser.user_id == id)
        .count()
      ),
    }


def format_user_with_info(user: User, role: UserRole) -> dict:
  user_dict = user.format_user(role)
  if role == UserRole.ADMIN and user.role == UserRole.DELIVERY:
    delivery_user_info = get_user_info(user.id, DeliveryUserInfo)
    if delivery_user_info:
      user_dict['delivery_user_info'] = delivery_user_info.to_dict()
  elif role in [UserRole.ADMIN, UserRole.OPERATOR] and user.role == UserRole.CUSTOMER:
    customer_user_info = get_user_info(user.id, CustomerUserInfo)
    if customer_user_info:
      user_dict['customer_user_info'] = customer_user_info.to_dict()
  return user_dict


def get_user_by_nickname(nickname: str) -> User | None:
  with Session() as session:
    return session.query(User).filter(User.nickname == nickname).first()


def get_user_info(user_id: int, klass) -> DeliveryUserInfo | CustomerUserInfo:
  if not hasattr(klass, 'user_id'):
    raise AttributeError(f"{klass.__name__} non ha l'attributo user_id")

  with Session() as session:
    return session.query(klass).filter(getattr(klass, 'user_id') == user_id).first()


def get_user_and_collection_point_by_code(code: str) -> tuple[User, CollectionPoint]:
  with Session() as session:
    return (
      session.query(User, CollectionPoint)
      .join(CustomerUserInfo, and_(User.id == CustomerUserInfo.user_id, CustomerUserInfo.code == code))
      .join(CollectionPoint, User.id == CollectionPoint.user_id)
      .first()
    )

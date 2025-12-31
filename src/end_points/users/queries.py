from database_api import Session
from ...database.enum import UserRole
from ...database.schema import User, ServiceUser, CollectionPoint, CustomerRule, Product, DeliveryUserInfo


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


def format_user_with_delivery_info(user: User, role: UserRole) -> dict:
  user_dict = user.format_user(role)
  if role == UserRole.ADMIN and user.role == UserRole.DELIVERY:
    delivery_user_info = get_delivery_user_info(user.id)
    if delivery_user_info:
      user_dict['delivery_user_info'] = delivery_user_info.to_dict()
  return user_dict


def get_user_by_nickname(nickname: str) -> User | None:
  with Session() as session:
    return session.query(User).filter(User.nickname == nickname).first()


def get_delivery_user_info(user_id: int) -> DeliveryUserInfo:
  with Session() as session:
    return session.query(DeliveryUserInfo).filter(DeliveryUserInfo.user_id == user_id).first()

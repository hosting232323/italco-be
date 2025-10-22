from datetime import datetime, date
from sqlalchemy import and_, not_, desc

from ...database.schema import (
  Order,
  OrderServiceUser,
  ServiceUser,
  Service,
  User,
  CollectionPoint,
  Photo,
  Schedule,
  DeliveryGroup,
  CustomerGroup,
  Motivation,
)
from database_api import Session
from ...database.enum import UserRole, OrderType, OrderStatus


def query_orders(
  user: User, filters: list
) -> list[tuple[Order, OrderServiceUser, ServiceUser, Service, User, CollectionPoint]]:
  with Session() as session:
    query = (
      session.query(Order, OrderServiceUser, ServiceUser, Service, User, CollectionPoint)
      .outerjoin(CollectionPoint, Order.collection_point_id == CollectionPoint.id)
      .outerjoin(OrderServiceUser, OrderServiceUser.order_id == Order.id)
      .outerjoin(ServiceUser, OrderServiceUser.service_user_id == ServiceUser.id)
      .outerjoin(Service, ServiceUser.service_id == Service.id)
      .outerjoin(User, ServiceUser.user_id == User.id)
    )

    if user.role == UserRole.CUSTOMER:
      query = query.filter(User.id == user.id)

    for filter in filters:
      model = globals()[filter['model']]
      field = getattr(model, filter['field'])
      value = filter['value']

      if model == Schedule:
        query = query.outerjoin(Schedule, Schedule.id == Order.schedule_id)
      elif model == CustomerGroup:
        query = query.outerjoin(CustomerGroup, CustomerGroup.id == User.customer_group_id)
      elif model == DeliveryGroup:
        query = query.outerjoin(Schedule, Schedule.id == Order.schedule_id).outerjoin(
          DeliveryGroup, DeliveryGroup.id == Schedule.delivery_group_id
        )

      if model == Order and field in [Order.created_at, Order.booking_date]:
        query = query.filter(
          field >= (value[0] if isinstance(value[0], date) else datetime.strptime(value[0], '%Y-%m-%d')),
          field <= (value[1] if isinstance(value[1], date) else datetime.strptime(value[1], '%Y-%m-%d')),
        )
      elif model == Order and field == Order.addressee:
        query = query.filter(field.ilike(f'%{value}%'))
      else:
        query = query.filter(field == value)

    return query.order_by(desc(Order.updated_at)).all()


def query_delivery_orders(
  user: User,
) -> list[tuple[Order, OrderServiceUser, ServiceUser, Service, User, CollectionPoint]]:
  with Session() as session:
    return (
      session.query(Order, OrderServiceUser, ServiceUser, Service, User, CollectionPoint)
      .outerjoin(CollectionPoint, Order.collection_point_id == CollectionPoint.id)
      .outerjoin(OrderServiceUser, OrderServiceUser.order_id == Order.id)
      .outerjoin(ServiceUser, OrderServiceUser.service_user_id == ServiceUser.id)
      .outerjoin(Service, ServiceUser.service_id == Service.id)
      .outerjoin(User, ServiceUser.user_id == User.id)
      .join(
        Schedule,
        and_(
          Schedule.delivery_group_id == user.delivery_group_id,
          Schedule.date == datetime.now().date(),
          Schedule.id == Order.schedule_id,
          not_(Order.status.in_([OrderStatus.PENDING])),
        ),
      )
      .all()
    )


def query_order_service_users(order: Order) -> list[OrderServiceUser]:
  with Session() as session:
    return session.query(OrderServiceUser).filter(OrderServiceUser.order_id == order.id).all()


def query_service_users(service_ids: list[int], user_id: int, type: OrderType) -> list[ServiceUser]:
  with Session() as session:
    return (
      session.query(ServiceUser)
      .join(Service, Service.id == ServiceUser.service_id)
      .filter(ServiceUser.user_id == user_id, ServiceUser.service_id.in_(service_ids), Service.type == type)
      .all()
    )


def format_query_result(
  tupla: tuple[Order, OrderServiceUser, ServiceUser, Service, User, CollectionPoint],
  list: list[dict],
  user: User,
) -> list[dict]:
  for element in list:
    if element['id'] == tupla[0].id:
      add_service(element, tupla[3], tupla[1], tupla[2].price)
      return list

  output = {
    **tupla[0].to_dict(),
    'price': 0,
    'products': {},
    'collection_point': tupla[5].to_dict(),
    'user': tupla[4].format_user(user.role),
  }
  add_service(output, tupla[3], tupla[1], tupla[2].price)
  list.append(output)
  return list


def add_service(object: dict, service: Service, order_service_user: OrderServiceUser, price: float) -> dict:
  if order_service_user.product not in object['products'].keys():
    object['products'][order_service_user.product] = []

  if next(
    (s for s in object['products'][order_service_user.product] if s['order_service_user_id'] == order_service_user.id),
    None,
  ):
    return object

  object['price'] += price
  object['products'][order_service_user.product].append(service.to_dict())
  object['products'][order_service_user.product][-1]['order_service_user_id'] = order_service_user.id
  return object


def query_delivery_group(schedule_id: int) -> DeliveryGroup:
  with Session() as session:
    return (
      session.query(DeliveryGroup)
      .join(Schedule, Schedule.delivery_group_id == DeliveryGroup.id)
      .filter(Schedule.id == schedule_id)
      .first()
    )


def get_order_photo_ids(order_id: int) -> list[int]:
  with Session() as session:
    photo_ids = session.query(Photo.id).filter(Photo.order_id == order_id).all()
  return [pid[0] for pid in photo_ids]


def get_motivations_by_order_id(order_id: int) -> list[Motivation]:
  with Session() as session:
    return session.query(Motivation).filter(Motivation.id_order == order_id).all()


def get_user_by_order(order: Order) -> User:
  with Session() as session:
    return session.query(User).join(
      ServiceUser, ServiceUser.user_id == User.id
    ).join(
      OrderServiceUser, and_(
        OrderServiceUser.service_user_id == ServiceUser.id,
        OrderServiceUser.order_id == order.id
      )
    ).first()

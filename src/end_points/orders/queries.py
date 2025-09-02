from datetime import datetime
from sqlalchemy import and_, not_

from ...database.schema import (
  Order,
  OrderServiceUser,
  ServiceUser,
  Service,
  ItalcoUser,
  CollectionPoint,
  Photo,
  Schedule,
  DeliveryGroup,
  CustomerGroup,
)
from ...database.enum import UserRole, OrderType, OrderStatus
from database_api import Session


def query_orders(
  user: ItalcoUser, filters: list, date_filter={}
) -> list[tuple[Order, OrderServiceUser, ServiceUser, Service, ItalcoUser, CollectionPoint, Photo]]:
  with Session() as session:
    query = (
      session.query(Order, OrderServiceUser, ServiceUser, Service, ItalcoUser, CollectionPoint, Photo)
      .outerjoin(CollectionPoint, Order.collection_point_id == CollectionPoint.id)
      .outerjoin(OrderServiceUser, OrderServiceUser.order_id == Order.id)
      .outerjoin(ServiceUser, OrderServiceUser.service_user_id == ServiceUser.id)
      .outerjoin(Service, ServiceUser.service_id == Service.id)
      .outerjoin(ItalcoUser, ServiceUser.user_id == ItalcoUser.id)
      .outerjoin(Photo, Photo.order_id == Order.id)
    )

    if user.role == UserRole.CUSTOMER:
      query = query.filter(ItalcoUser.id == user.id)

    for filter in filters:
      if filter['model'] == 'Schedule':
        query = query.outerjoin(Schedule, Schedule.id == Order.schedule_id)
      elif filter['model'] == 'CustomerGroup':
        query = query.outerjoin(CustomerGroup, CustomerGroup.id == ItalcoUser.customer_group_id)
      elif filter['model'] == 'DeliveryGroup':
        query = query.outerjoin(Schedule, Schedule.id == Order.schedule_id).outerjoin(
          DeliveryGroup, DeliveryGroup.id == Schedule.delivery_group_id
        )

      query = query.filter(getattr(globals()[filter['model']], filter['field']) == filter['value'])

    if date_filter != {}:
      query = query.filter(
        Order.booking_date >= datetime.strptime(date_filter['start_date'], '%Y-%m-%d'),
        Order.booking_date <= datetime.strptime(date_filter['end_date'], '%Y-%m-%d'),
      )

    return query.all()


def query_delivery_orders(
  user: ItalcoUser,
) -> list[tuple[Order, OrderServiceUser, ServiceUser, Service, ItalcoUser, CollectionPoint, Photo]]:
  with Session() as session:
    return (
      session.query(Order, OrderServiceUser, ServiceUser, Service, ItalcoUser, CollectionPoint, Photo)
      .outerjoin(CollectionPoint, Order.collection_point_id == CollectionPoint.id)
      .outerjoin(OrderServiceUser, OrderServiceUser.order_id == Order.id)
      .outerjoin(ServiceUser, OrderServiceUser.service_user_id == ServiceUser.id)
      .outerjoin(Service, ServiceUser.service_id == Service.id)
      .outerjoin(ItalcoUser, ServiceUser.user_id == ItalcoUser.id)
      .outerjoin(Photo, Photo.order_id == Order.id)
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
  tupla: tuple[Order, OrderServiceUser, ServiceUser, Service, ItalcoUser, CollectionPoint, Photo],
  list: list[dict],
  user: ItalcoUser,
) -> list[dict]:
  for element in list:
    if element['id'] == tupla[0].id:
      add_photo(element, tupla[6])
      add_service(element, tupla[3], tupla[1], tupla[2].price)
      return list

  output = {
    **tupla[0].to_dict(),
    'price': 0,
    'photos': [],
    'products': {},
    'collection_point': tupla[5].to_dict(),
    'user': tupla[4].format_user(user.role),
  }
  add_photo(output, tupla[6])
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


def add_photo(object: dict, photo: Photo) -> dict:
  if not photo or photo.id in object['photos']:
    return object

  object['photos'].append(photo.id)
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

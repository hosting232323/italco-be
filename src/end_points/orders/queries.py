from datetime import datetime, date
from sqlalchemy import and_, not_, desc

from database_api import Session
from ...database.enum import UserRole, OrderType, OrderStatus
from ...database.schema import (
  Order,
  Product,
  ServiceUser,
  Service,
  User,
  CollectionPoint,
  Photo,
  Schedule,
  DeliveryGroup,
  CustomerGroup,
  Motivation,
  ScheduleItem,
  ScheduleItemOrder,
)


def query_orders(
  user: User, filters: list, limit: int = None
) -> list[tuple[Order, Product, ServiceUser, Service, User, CollectionPoint]]:
  with Session() as session:
    query = (
      session.query(Order, Product, ServiceUser, Service, User, CollectionPoint)
      .outerjoin(Product, Product.order_id == Order.id)
      .outerjoin(CollectionPoint, Product.collection_point_id == CollectionPoint.id)
      .outerjoin(ServiceUser, Product.service_user_id == ServiceUser.id)
      .outerjoin(Service, ServiceUser.service_id == Service.id)
      .outerjoin(User, ServiceUser.user_id == User.id)
    )

    if user.role == UserRole.CUSTOMER:
      query = query.filter(User.id == user.id)

    for filter in filters:
      model = globals()[filter['model']] if filter['model'] not in ['CustomerUser', 'DeliveryUser'] else User
      field = getattr(model, filter['field'])
      value = filter['value']

      if filter['model'] == 'DeliveryUser' and field == User.id:
        query = (
          query
          .join(ScheduleItemOrder, ScheduleItemOrder.order_id == Order.id)
          .join(ScheduleItem, ScheduleItem.id == ScheduleItemOrder.schedule_item_id)
          .join(Schedule, Schedule.id == ScheduleItem.schedule_id)
          .join(DeliveryGroup, and_(DeliveryGroup.schedule_id == Schedule.id, DeliveryGroup.user_id == value))
        )
        continue

      if model in [Schedule]:
        query = (
          query
          .join(ScheduleItemOrder, ScheduleItemOrder.order_id == Order.id)
          .join(ScheduleItem, ScheduleItem.id == ScheduleItemOrder.schedule_item_id)
          .join(Schedule, Schedule.id == ScheduleItem.schedule_id)
        )
      elif model == CustomerGroup:
        query = query.join(CustomerGroup, CustomerGroup.id == User.customer_group_id)

      if model == Order and field in [Order.created_at, Order.booking_date]:
        query = query.filter(
          field >= (value[0] if isinstance(value[0], date) else datetime.strptime(value[0], '%Y-%m-%d')),
          field <= (value[1] if isinstance(value[1], date) else datetime.strptime(value[1], '%Y-%m-%d')),
        )
      elif model == Order and field == Order.addressee:
        query = query.filter(field.ilike(f'%{value}%'))
      elif model == Order and field == Order.id and type(value) is list:
        query = query.filter(Order.id.in_(value))
      else:
        query = query.filter(field == value)

    query = query.order_by(desc(Order.created_at))
    if limit:
      query = query.limit(limit)
    return query.all()


def query_delivery_orders(
  user: User,
) -> list[tuple[Order, Product, ServiceUser, Service, User, CollectionPoint]]:
  with Session() as session:
    return (
      session.query(Order, Product, ServiceUser, Service, User, CollectionPoint)
      .join(ScheduleItemOrder, ScheduleItemOrder.order_id == Order.id)
      .join(ScheduleItem, ScheduleItem.id == ScheduleItemOrder.schedule_item_id)
      .join(
        Schedule,
        and_(
          Schedule.date == datetime.now().date(),
          Schedule.id == ScheduleItem.schedule_id,
          not_(Order.status.in_([OrderStatus.PENDING])),
        ),
      )
      .join(DeliveryGroup, and_(DeliveryGroup.schedule_id == Schedule.id, DeliveryGroup.user_id == user.id))
      .outerjoin(Product, Product.order_id == Order.id)
      .outerjoin(CollectionPoint, Product.collection_point_id == CollectionPoint.id)
      .outerjoin(ServiceUser, Product.service_user_id == ServiceUser.id)
      .outerjoin(Service, ServiceUser.service_id == Service.id)
      .outerjoin(User, ServiceUser.user_id == User.id)
      .all()
    )


def query_products(order: Order) -> list[Product]:
  with Session() as session:
    return session.query(Product).filter(Product.order_id == order.id).all()


def query_service_users(service_ids: list[int], user_id: int, type: OrderType) -> list[ServiceUser]:
  with Session() as session:
    return (
      session.query(ServiceUser)
      .join(Service, Service.id == ServiceUser.service_id)
      .filter(ServiceUser.user_id == user_id, ServiceUser.service_id.in_(service_ids), Service.type == type)
      .all()
    )


def format_query_result(
  tupla: tuple[Order, Product, ServiceUser, Service, User, CollectionPoint],
  list: list[dict],
  user: User,
) -> list[dict]:
  for element in list:
    if element['id'] == tupla[0].id:
      add_service(element, tupla[3], tupla[1], tupla[5], tupla[2].price)
      return list

  output = {
    **tupla[0].to_dict(),
    'price': 0,
    'products': {},
    'user': tupla[4].format_user(user.role),
  }
  add_service(output, tupla[3], tupla[1], tupla[5], tupla[2].price)
  list.append(output)
  return list


def add_service(
  object: dict, service: Service, product: Product, collection_point: CollectionPoint, price: float
) -> dict:
  if product.name not in object['products'].keys():
    object['products'][product.name] = {'services': [], 'collection_point': collection_point.to_dict()}

  if next(
    (s for s in object['products'][product.name]['services'] if s['product_id'] == product.id),
    None,
  ):
    return

  object['price'] += price
  object['products'][product.name]['services'].append(service.to_dict())
  object['products'][product.name]['services'][-1]['product_id'] = product.id


def get_order_photo_ids(order_id: int) -> list[int]:
  with Session() as session:
    return [pid[0] for pid in session.query(Photo.id).filter(Photo.order_id == order_id).all()]


def get_motivations_by_order_id(order_id: int) -> list[Motivation]:
  with Session() as session:
    return session.query(Motivation).filter(Motivation.id_order == order_id).all()


def get_customer_user_by_order(order: Order) -> User:
  with Session() as session:
    return (
      session.query(User)
      .join(ServiceUser, ServiceUser.user_id == User.id)
      .join(Product, and_(Product.service_user_id == ServiceUser.id, Product.order_id == order.id))
      .first()
    )


def get_delivery_user_by_schedule_id(schedule_id: int) -> User:
  with Session() as session:
    return (
      session.query(User)
      .join(DeliveryGroup, and_(DeliveryGroup.user_id == User.id, DeliveryGroup.schedule_id == schedule_id))
      .first()
    )


def get_selling_point(order: Order) -> User:
  with Session() as session:
    return (
      session.query(User)
      .join(ServiceUser, User.id == ServiceUser.user_id)
      .join(Product, and_(ServiceUser.id == Product.service_user_id, Product.order_id == order.id))
      .first()
    )

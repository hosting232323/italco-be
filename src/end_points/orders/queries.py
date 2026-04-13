from sqlalchemy import and_, desc, or_, cast, Date

from database_api import Session
from ...utils.date import handle_date
from ...database.enum import UserRole, OrderType
from ...database.schema import (
  Order,
  History,
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
      value = filter['value']
      if filter['field'] == 'work_date':
        if type(value) is list:
          query = query.filter(
            or_(
              and_(Order.booking_date >= handle_date(value[0]), Order.booking_date <= handle_date(value[1])),
              and_(Order.dpc >= handle_date(value[0]), Order.dpc <= handle_date(value[1])),
            )
          )
        else:
          query = query.filter(or_(Order.booking_date == handle_date(value), Order.dpc == handle_date(value)))
        continue

      model = globals()[filter['model']] if filter['model'] not in ['CustomerUser', 'DeliveryUser'] else User
      field = getattr(model, filter['field'])
      if filter['model'] == 'DeliveryUser' and field == User.id:
        query = (
          query.join(ScheduleItemOrder, ScheduleItemOrder.order_id == Order.id)
          .join(ScheduleItem, ScheduleItem.id == ScheduleItemOrder.schedule_item_id)
          .join(Schedule, Schedule.id == ScheduleItem.schedule_id)
          .join(DeliveryGroup, and_(DeliveryGroup.schedule_id == Schedule.id, DeliveryGroup.user_id == value))
        )
        continue

      if model == Schedule:
        query = (
          query.join(ScheduleItemOrder, ScheduleItemOrder.order_id == Order.id)
          .join(ScheduleItem, ScheduleItem.id == ScheduleItemOrder.schedule_item_id)
          .join(Schedule, Schedule.id == ScheduleItem.schedule_id)
        )
      elif model == CustomerGroup:
        query = query.join(CustomerGroup, CustomerGroup.id == User.customer_group_id)

      if (
        model == Order
        and type(value) is list
        and field
        in [
          Order.created_at,
          Order.dpc,
          Order.booking_date,
          Order.drc,
          Order.updated_at,
          Order.confirmation_date,
          Order.completion_date,
        ]
      ):
        query = query.filter(field >= handle_date(value[0]), field <= handle_date(value[1]))
      elif model == Order and field in [Order.created_at, Order.updated_at]:
        query = query.filter(cast(field, Date) == value)
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
    (service for service in object['products'][product.name]['services'] if service['product_id'] == product.id),
    None,
  ):
    return

  object['price'] += price
  object['products'][product.name]['services'].append(service.to_dict())
  object['products'][product.name]['services'][-1]['product_id'] = product.id
  object['products'][product.name]['rae_product_id'] = product.rae_product_id
  object['products'][product.name]['rae_product_quantity'] = product.rae_product_quantity


def get_order_photos(order_id: int) -> list[Photo]:
  with Session() as session:
    return session.query(Photo).filter(Photo.order_id == order_id).all()


def get_motivations_by_order_id(order_id: int) -> list[Motivation]:
  with Session() as session:
    return session.query(Motivation).filter(Motivation.order_id == order_id).all()


def get_selling_point(order: Order) -> User:
  with Session() as session:
    return (
      session.query(User)
      .join(ServiceUser, User.id == ServiceUser.user_id)
      .join(Product, and_(ServiceUser.id == Product.service_user_id, Product.order_id == order.id))
      .first()
    )


def get_order_by_external_id_and_customer(external_id: str, customer_id: str) -> Order:
  with Session() as session:
    return (
      session.query(Order)
      .join(Product, and_(Order.id == Product.order_id, Order.external_id == external_id))
      .join(ServiceUser, and_(Product.service_user_id == ServiceUser.id, ServiceUser.user_id == customer_id))
      .first()
    )


def get_order_by_external_id(external_id: str) -> Order:
  with Session() as session:
    return session.query(Order).filter(Order.external_id == external_id).first()


def get_all_histories_by_order_id(order_id: int) -> list[History]:
  with Session() as session:
    return session.query(History).filter(History.order_id == order_id).order_by(History.created_at).all()

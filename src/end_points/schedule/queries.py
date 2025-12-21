from datetime import datetime, date
from sqlalchemy import and_, desc, or_
from sqlalchemy.orm import Session as session_type

from database_api import Session
from ...database.enum import ScheduleType
from database_api.operations import db_session_decorator
from ...database.schema import (
  Schedule,
  User,
  Order,
  DeliveryGroup,
  Transport,
  ScheduleItem,
  ScheduleItemCollectionPoint,
  ScheduleItemOrder,
  CollectionPoint,
)


def query_schedules(
  filters: list, limit: int = None
) -> list[tuple[Schedule, Transport, ScheduleItem, CollectionPoint, Order, User]]:
  with Session() as session:
    query = (
      session.query(Schedule, Transport, ScheduleItem, CollectionPoint, Order, User)
      .join(Transport, Schedule.transport_id == Transport.id)
      .join(ScheduleItem, ScheduleItem.schedule_id == Schedule.id)
      .outerjoin(
        ScheduleItemCollectionPoint,
        and_(
          ScheduleItem.operation_type == ScheduleType.COLLECTIONPOINT,
          ScheduleItemCollectionPoint.schedule_item_id == ScheduleItem.id,
        ),
      )
      .outerjoin(CollectionPoint, CollectionPoint.id == ScheduleItemCollectionPoint.collection_point_id)
      .outerjoin(
        ScheduleItemOrder,
        and_(ScheduleItem.operation_type == ScheduleType.ORDER, ScheduleItemOrder.schedule_item_id == ScheduleItem.id),
      )
      .outerjoin(Order, ScheduleItemOrder.order_id == Order.id)
      .join(DeliveryGroup, DeliveryGroup.schedule_id == Schedule.id)
      .join(User, DeliveryGroup.user_id == User.id)
      .order_by(desc(Schedule.updated_at))
    )
    for filter in filters:
      model = globals()[filter['model']]
      field = getattr(model, filter['field'])
      value = filter['value']

      if model == Schedule and field in [Schedule.created_at, Schedule.date]:
        query = query.filter(
          field >= (value[0] if isinstance(value[0], date) else datetime.strptime(value[0], '%Y-%m-%d')),
          field <= (value[1] if isinstance(value[1], date) else datetime.strptime(value[1], '%Y-%m-%d')),
        )
      else:
        query = query.filter(field == value)

    query = query.order_by(desc(Schedule.created_at))
    if limit:
      query = query.limit(limit)
    return query.all()


def query_schedules_count(user_id, schedule_date) -> int:
  with Session() as session:
    return (
      session.query(DeliveryGroup)
      .join(
        Schedule,
        and_(
          DeliveryGroup.schedule_id == Schedule.id, DeliveryGroup.user_id == user_id, Schedule.date == schedule_date
        ),
      )
      .count()
    )


def get_schedule_item_by_order(order: Order) -> ScheduleItem:
  with Session() as session:
    return (
      session.query(ScheduleItem)
      .join(
        ScheduleItemOrder,
        and_(
          ScheduleItemOrder.order_id == order.id,
          ScheduleItem.operation_type == ScheduleType.ORDER,
          ScheduleItemOrder.schedule_item_id == ScheduleItem.id,
        ),
      )
      .first()
    )


def format_query_result(
  tupla: tuple[Schedule, Transport, ScheduleItem, CollectionPoint, Order, User], list: list[dict], user: User
) -> list[dict]:
  for element in list:
    if element['id'] == tupla[0].id:
      format_schedule_item(element['schedule_items'], tupla[2], tupla[3], tupla[4])
      if tupla[5] and tupla[5].id not in [user['id'] for user in element['users']]:
        element['users'].append(tupla[5].format_user(user.role))
      return list

  schedule = {
    **tupla[0].to_dict(),
    'transport': tupla[1].to_dict(),
    'users': [tupla[5].format_user(user.role)] if tupla[5] else [],
    'schedule_items': [],
  }
  format_schedule_item(schedule['schedule_items'], tupla[2], tupla[3], tupla[4])
  list.append(schedule)
  return list


def format_schedule_item(
  schedule_items: list, schedule_item: ScheduleItem, collection_point: CollectionPoint, order: Order
):
  if (
    schedule_item.operation_type == ScheduleType.ORDER
    and order
    and order.id not in [item['order_id'] for item in schedule_items if 'order_id' in item]
  ):
    item = order.to_dict()
    item['order_id'] = order.id
  elif (
    schedule_item.operation_type == ScheduleType.COLLECTIONPOINT
    and collection_point
    and collection_point.id
    not in [item['collection_point_id'] for item in schedule_items if 'collection_point_id' in item]
  ):
    item = collection_point.to_dict()
    item['collection_point_id'] = collection_point.id
  else:
    return

  item['id'] = schedule_item.id
  item['index'] = schedule_item.index
  item['operation_type'] = schedule_item.operation_type.value
  item['end_time_slot'] = schedule_item.end_time_slot.strftime('%H:%M:%S')
  item['start_time_slot'] = schedule_item.start_time_slot.strftime('%H:%M:%S')
  schedule_items.append(item)


@db_session_decorator(commit=False)
def get_schedule_items(
  schedule: Schedule, session: session_type = None
) -> list[tuple[ScheduleItem, ScheduleItemCollectionPoint, ScheduleItemOrder]]:
  return (
    session.query(ScheduleItem, ScheduleItemCollectionPoint, ScheduleItemOrder)
    .outerjoin(
      ScheduleItemCollectionPoint,
      and_(
        ScheduleItem.schedule_id == schedule.id,
        ScheduleItemCollectionPoint.schedule_item_id == ScheduleItem.id,
        ScheduleItem.operation_type == ScheduleType.COLLECTIONPOINT,
      ),
    )
    .outerjoin(
      ScheduleItemOrder,
      and_(
        ScheduleItem.schedule_id == schedule.id,
        ScheduleItemOrder.schedule_item_id == ScheduleItem.id,
        ScheduleItem.operation_type == ScheduleType.ORDER,
      ),
    )
    .filter(ScheduleItem.schedule_id == schedule.id)
    .all()
  )


def get_delivery_groups(schedule: Schedule) -> list[DeliveryGroup]:
  with Session() as session:
    return session.query(DeliveryGroup).filter(DeliveryGroup.schedule_id == schedule.id).all()


def get_delivery_groups_by_order_id(order_id: int) -> list[DeliveryGroup]:
  with Session() as session:
    return (
      session.query(DeliveryGroup)
      .join(
        Schedule,
        DeliveryGroup.schedule_id == Schedule.id,
      )
      .join(
        ScheduleItem,
        ScheduleItem.schedule_id == Schedule.id,
      )
      .join(
        ScheduleItemOrder,
        and_(
          ScheduleItemOrder.schedule_item_id == ScheduleItem.id,
          ScheduleItemOrder.order_id == order_id,
          ScheduleItem.operation_type == ScheduleType.ORDER,
        ),
      )
      .all()
    )


def get_delivery_users_by_date(date: datetime) -> list[User]:
  with Session() as session:
    return (
      session.query(User)
      .outerjoin(DeliveryGroup, User.id == DeliveryGroup.user_id)
      .outerjoin(Schedule, Schedule.id == DeliveryGroup.schedule_id)
      .filter(or_(Schedule.date != date, Schedule.id.is_(None)))
      .all()
    )


def get_transports_by_date(date: datetime) -> list[Transport]:
  with Session() as session:
    return (
      session.query(Transport)
      .outerjoin(Schedule, Schedule.transport_id == Transport.id)
      .filter(or_(Schedule.date != date, Schedule.id.is_(None)))
      .all()
    )

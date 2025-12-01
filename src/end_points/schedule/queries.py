from sqlalchemy import and_, desc
from datetime import datetime, date

from database_api import Session
from ...database.schema import Schedule, User, Order, DeliveryGroup, Transport


def query_schedules(filters: list, limit: int = None) -> list[tuple[Schedule, Transport, Order, User]]:
  with Session() as session:
    query = (
      session.query(Schedule, Transport, Order, User)
      .join(Transport, Schedule.transport_id == Transport.id)
      .join(Order, Order.schedule_id == Schedule.id)
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


def get_related_orders(schedule: Schedule) -> list[Order]:
  with Session() as session:
    return session.query(Order).filter(Order.schedule_id == schedule.id).all()


def format_query_result(tupla: tuple[Schedule, Transport, Order, User], list: list[dict], user: User) -> list[dict]:
  for element in list:
    if element['id'] == tupla[0].id:
      if tupla[2] and tupla[2].id not in [order['id'] for order in element['orders']]:
        element['orders'].append(tupla[2].to_dict())
      if tupla[3] and tupla[3].id not in [user['id'] for user in element['users']]:
        element['users'].append(tupla[3].format_user(user.role))
      return list

  list.append(
    {
      **tupla[0].to_dict(),
      'transport': tupla[1].to_dict(),
      'users': [tupla[3].format_user(user.role)] if tupla[3] else [],
      'orders': [tupla[2].to_dict()] if tupla[2] else [],
    }
  )
  return list


def get_delivery_groups(schedule: Schedule) -> list[DeliveryGroup]:
  with Session() as session:
    return session.query(DeliveryGroup).filter(DeliveryGroup.schedule_id == schedule.id).all()

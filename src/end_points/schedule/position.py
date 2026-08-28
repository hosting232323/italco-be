from database_api.operations import create, get_by_id

from ...database.enum import ScheduleItemUserType
from ...database.schema import Schedule, ScheduleItemUser, User
from .queries import get_delivery_groups, get_latest_schedule_item_user


def _user_in_schedule(schedule: Schedule, user: User) -> bool:
  return any(delivery_group.user_id == user.id for delivery_group in get_delivery_groups(schedule))


def _format_holder(schedule_item_user: ScheduleItemUser) -> dict:
  holder_user: User = get_by_id(User, schedule_item_user.user_id)
  return {**holder_user.format_user(), 'type': schedule_item_user.type.value}


def get_schedule_position(user: User, schedule_id: int) -> dict:
  schedule: Schedule = get_by_id(Schedule, schedule_id)
  if not schedule or not _user_in_schedule(schedule, user):
    return {'status': 'ko', 'message': 'Borderò non trovato'}

  latest = get_latest_schedule_item_user(schedule_id)
  if latest is None or latest.type == ScheduleItemUserType.CLOSING:
    return {'status': 'ok', 'holder': None}

  return {'status': 'ok', 'holder': _format_holder(latest)}


def claim_schedule_position(user: User, schedule_id: int) -> dict:
  """Attiva la posizione per il borderò, o la prende in carico se è già tenuta
  da un collega. Idempotente se il chiamante è già l'holder corrente."""
  schedule: Schedule = get_by_id(Schedule, schedule_id)
  if not schedule or not _user_in_schedule(schedule, user):
    return {'status': 'ko', 'message': 'Borderò non trovato'}

  latest = get_latest_schedule_item_user(schedule_id)
  is_active = latest is not None and latest.type != ScheduleItemUserType.CLOSING
  if is_active and latest.user_id == user.id:
    return {'status': 'ok', 'holder': _format_holder(latest)}

  event_type = ScheduleItemUserType.CHANGE if is_active else ScheduleItemUserType.OPENING
  event = create(ScheduleItemUser, {'schedule_id': schedule_id, 'user_id': user.id, 'type': event_type})
  return {'status': 'ok', 'holder': _format_holder(event)}

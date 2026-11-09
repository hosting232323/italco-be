from database_api.operations import create, get_by_id

from ...database.enum import ScheduleItemUserType
from ...database.schema import Schedule, ScheduleItemUser, User
from .queries import get_schedule_delivery_users, get_latest_schedule_item_user

NOT_HOLDER_MESSAGE = (
  'Solo il corriere che ha attivato la posizione può modificare il borderò: '
  'attivala dal banner oppure prendi il controllo.'
)


def _user_in_schedule(schedule: Schedule, user: User) -> bool:
  return any(delivery_user.id == user.id for delivery_user in get_schedule_delivery_users(schedule))


def _format_holder(schedule_item_user: ScheduleItemUser) -> dict:
  holder_user: User = get_by_id(User, schedule_item_user.user_id)
  return {**holder_user.format_user(), 'type': schedule_item_user.type.value}


def _parse_coordinates(coordinates: dict | None) -> tuple[float, float] | None:
  try:
    lat = float(coordinates['lat'])
    lon = float(coordinates['lon'])
  except (TypeError, KeyError, ValueError):
    return None
  if not (-90 <= lat <= 90 and -180 <= lon <= 180):
    return None
  return lat, lon


def user_holds_schedule_position(user: User, schedule_id: int) -> bool:
  """Vero se `user` e' l'attuale holder della posizione del borderò."""
  latest = get_latest_schedule_item_user(schedule_id)
  return latest is not None and latest.type != ScheduleItemUserType.CLOSING and latest.user_id == user.id


def holder_required_error(user: User, schedule_id: int) -> dict | None:
  """Errore da restituire quando `user` non tiene la posizione del borderò.

  Con più corrieri sullo stesso borderò può modificarlo solo chi ha attivato la
  posizione; gli altri lo vedono in sola lettura. None = può procedere.
  """
  if user_holds_schedule_position(user, schedule_id):
    return None
  return {'status': 'ko', 'message': NOT_HOLDER_MESSAGE, 'code': 'position_not_held'}


def get_schedule_position(user: User, schedule_id: int) -> dict:
  schedule: Schedule = get_by_id(Schedule, schedule_id)
  if not schedule or not _user_in_schedule(schedule, user):
    return {'status': 'ko', 'message': 'Borderò non trovato'}

  latest = get_latest_schedule_item_user(schedule_id)
  if latest is None or latest.type == ScheduleItemUserType.CLOSING:
    return {'status': 'ok', 'holder': None}

  return {'status': 'ok', 'holder': _format_holder(latest)}


def claim_schedule_position(user: User, schedule_id: int, coordinates: dict | None = None) -> dict:
  """Attiva la posizione per il borderò, o la prende in carico se è già tenuta
  da un collega. Idempotente se il chiamante è già l'holder corrente.

  Servono le coordinate lette dal device in questo momento: sono la prova che
  il GPS funziona davvero. Senza, l'app mostrerebbe "stai condividendo" con il
  permesso negato o il GPS spento e il gestionale non vedrebbe mai il corriere.
  """
  schedule: Schedule = get_by_id(Schedule, schedule_id)
  if not schedule or not _user_in_schedule(schedule, user):
    return {'status': 'ko', 'message': 'Borderò non trovato'}

  parsed = _parse_coordinates(coordinates)
  if parsed is None:
    return {
      'status': 'ko',
      'message': 'Posizione non disponibile: attiva il GPS e consenti l’accesso alla posizione, poi riprova.',
      'code': 'position_required',
    }

  # Import locale: il modulo users importa a sua volta parti dell'app.
  from ..users import save_user_info
  from ...database.schema import DeliveryUserInfo

  save_user_info(user.id, {'lat': parsed[0], 'lon': parsed[1]}, DeliveryUserInfo)

  latest = get_latest_schedule_item_user(schedule_id)
  is_active = latest is not None and latest.type != ScheduleItemUserType.CLOSING
  if is_active and latest.user_id == user.id:
    return {'status': 'ok', 'holder': _format_holder(latest)}

  event_type = ScheduleItemUserType.CHANGE if is_active else ScheduleItemUserType.OPENING
  event = create(ScheduleItemUser, {'schedule_id': schedule_id, 'user_id': user.id, 'type': event_type})
  return {'status': 'ok', 'holder': _format_holder(event)}

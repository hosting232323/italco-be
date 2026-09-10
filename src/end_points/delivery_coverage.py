from datetime import datetime

from sqlalchemy import asc, desc
from sqlalchemy.orm import joinedload
from flask import Blueprint, request

from database_api import Session
from ..database.enum import UserRole
from . import flask_session_authentication
from database_api.operations import create, delete, update, get_by_id
from ..database.schema import User, DeliveryCoverage, DeliveryCoverageDay, DeliveryAbsence


delivery_coverage_bp = Blueprint('delivery_coverage_bp', __name__)

# Admin e operatori gestiscono la copertura; il super admin che opera in una
# company passa comunque, come ovunque (bypass in flask_session_authentication).
COVERAGE_ROLES = [UserRole.ADMIN, UserRole.OPERATOR]


def _parse_date(value: str):
  return datetime.strptime(value, '%Y-%m-%d').date()


def _parse_time(value: str):
  for fmt in ['%H:%M', '%H:%M:%S']:
    try:
      return datetime.strptime(value, fmt).time()
    except ValueError:
      continue
  raise ValueError(f'Formato orario non riconosciuto: {value}')


def _delivery_user_or_none(user_id) -> User | None:
  # get_by_id gira dentro lo scope della richiesta: un id di un'altra company
  # torna None, quindi qui basta controllare il ruolo.
  target = get_by_id(User, int(user_id))
  if not target or target.role != UserRole.DELIVERY:
    return None
  return target


@delivery_coverage_bp.route('', methods=['GET'])
@flask_session_authentication(COVERAGE_ROLES)
def get_delivery_coverage(_):
  return {
    'status': 'ok',
    'delivery_users': [{'id': user.id, 'nickname': user.nickname} for user in query_delivery_users()],
    'coverages': query_coverages(),
    'absences': [absence.to_dict() for absence in query_absences()],
  }


@delivery_coverage_bp.route('', methods=['POST'])
@flask_session_authentication(COVERAGE_ROLES)
def create_delivery_coverage(_):
  if not _delivery_user_or_none(request.json['user_id']):
    return {'status': 'ko', 'message': 'Utente delivery non trovato'}

  start_date = _parse_date(request.json['start_date'])
  end_date = _parse_date(request.json['end_date'])
  if end_date < start_date:
    return {'status': 'ko', 'message': 'La data di fine deve essere successiva a quella di inizio'}

  coverage = create(
    DeliveryCoverage,
    {'user_id': int(request.json['user_id']), 'start_date': start_date, 'end_date': end_date},
  )
  return {'status': 'ok', 'coverage': get_coverage_dict(coverage.id)}


@delivery_coverage_bp.route('<id>', methods=['PUT'])
@flask_session_authentication(COVERAGE_ROLES)
def update_delivery_coverage(_, id):
  coverage: DeliveryCoverage = get_by_id(DeliveryCoverage, int(id))
  if not coverage:
    return {'status': 'ko', 'message': 'Copertura non trovata'}

  data = {}
  if 'start_date' in request.json:
    data['start_date'] = _parse_date(request.json['start_date'])
  if 'end_date' in request.json:
    data['end_date'] = _parse_date(request.json['end_date'])

  start_date = data.get('start_date', coverage.start_date)
  end_date = data.get('end_date', coverage.end_date)
  if end_date < start_date:
    return {'status': 'ko', 'message': 'La data di fine deve essere successiva a quella di inizio'}

  update(coverage, data)
  return {'status': 'ok', 'coverage': get_coverage_dict(int(id))}


@delivery_coverage_bp.route('<id>', methods=['DELETE'])
@flask_session_authentication(COVERAGE_ROLES)
def delete_delivery_coverage(_, id):
  coverage: DeliveryCoverage = get_by_id(DeliveryCoverage, int(id))
  if not coverage:
    return {'status': 'ko', 'message': 'Copertura non trovata'}

  delete(coverage)
  return {'status': 'ok', 'message': 'Operazione completata'}


@delivery_coverage_bp.route('<id>/day', methods=['POST'])
@flask_session_authentication(COVERAGE_ROLES)
def create_coverage_day(_, id):
  coverage: DeliveryCoverage = get_by_id(DeliveryCoverage, int(id))
  if not coverage:
    return {'status': 'ko', 'message': 'Copertura non trovata'}

  day_of_week = request.json['day_of_week']
  if day_of_week not in list(range(7)):
    raise ValueError('Invalid day_of_week value')

  start_time = _parse_time(request.json['start_time'])
  end_time = _parse_time(request.json['end_time'])
  if end_time <= start_time:
    return {'status': 'ko', 'message': "L'orario di fine deve essere successivo a quello di inizio"}

  if query_coverage_day(coverage.id, day_of_week):
    return {'status': 'ko', 'message': 'Giorno già presente in questa copertura'}

  day = create(
    DeliveryCoverageDay,
    {'coverage_id': coverage.id, 'day_of_week': day_of_week, 'start_time': start_time, 'end_time': end_time},
  )
  return {'status': 'ok', 'day': day.to_dict()}


@delivery_coverage_bp.route('day/<id>', methods=['PUT'])
@flask_session_authentication(COVERAGE_ROLES)
def update_coverage_day(_, id):
  day: DeliveryCoverageDay = get_by_id(DeliveryCoverageDay, int(id))
  if not day:
    return {'status': 'ko', 'message': 'Giorno non trovato'}

  data = {}
  if 'start_time' in request.json:
    data['start_time'] = _parse_time(request.json['start_time'])
  if 'end_time' in request.json:
    data['end_time'] = _parse_time(request.json['end_time'])

  start_time = data.get('start_time', day.start_time)
  end_time = data.get('end_time', day.end_time)
  if end_time <= start_time:
    return {'status': 'ko', 'message': "L'orario di fine deve essere successivo a quello di inizio"}

  return {'status': 'ok', 'day': update(day, data).to_dict()}


@delivery_coverage_bp.route('day/<id>', methods=['DELETE'])
@flask_session_authentication(COVERAGE_ROLES)
def delete_coverage_day(_, id):
  day: DeliveryCoverageDay = get_by_id(DeliveryCoverageDay, int(id))
  if not day:
    return {'status': 'ko', 'message': 'Giorno non trovato'}

  delete(day)
  return {'status': 'ok', 'message': 'Operazione completata'}


@delivery_coverage_bp.route('absence', methods=['POST'])
@flask_session_authentication(COVERAGE_ROLES)
def create_delivery_absence(_):
  if not _delivery_user_or_none(request.json['user_id']):
    return {'status': 'ko', 'message': 'Utente delivery non trovato'}

  start_date = _parse_date(request.json['start_date'])
  end_date = _parse_date(request.json['end_date'])
  if end_date < start_date:
    return {'status': 'ko', 'message': 'La data di fine deve essere successiva a quella di inizio'}

  absence = create(
    DeliveryAbsence,
    {
      'user_id': int(request.json['user_id']),
      'start_date': start_date,
      'end_date': end_date,
      'note': (request.json.get('note') or None),
    },
  )
  return {'status': 'ok', 'absence': absence.to_dict()}


@delivery_coverage_bp.route('absence/<id>', methods=['PUT'])
@flask_session_authentication(COVERAGE_ROLES)
def update_delivery_absence(_, id):
  absence: DeliveryAbsence = get_by_id(DeliveryAbsence, int(id))
  if not absence:
    return {'status': 'ko', 'message': 'Assenza non trovata'}

  data = {}
  if 'start_date' in request.json:
    data['start_date'] = _parse_date(request.json['start_date'])
  if 'end_date' in request.json:
    data['end_date'] = _parse_date(request.json['end_date'])
  if 'note' in request.json:
    data['note'] = request.json['note'] or None

  start_date = data.get('start_date', absence.start_date)
  end_date = data.get('end_date', absence.end_date)
  if end_date < start_date:
    return {'status': 'ko', 'message': 'La data di fine deve essere successiva a quella di inizio'}

  return {'status': 'ok', 'absence': update(absence, data).to_dict()}


@delivery_coverage_bp.route('absence/<id>', methods=['DELETE'])
@flask_session_authentication(COVERAGE_ROLES)
def delete_delivery_absence(_, id):
  absence: DeliveryAbsence = get_by_id(DeliveryAbsence, int(id))
  if not absence:
    return {'status': 'ko', 'message': 'Assenza non trovata'}

  delete(absence)
  return {'status': 'ok', 'message': 'Operazione completata'}


def format_coverage(coverage: DeliveryCoverage) -> dict:
  # Chiamata solo con `coverage` ancora legato a una sessione e days già
  # caricati (query_coverages, get_coverage_dict): fuori da lì il lazy load su
  # istanza scollegata solleverebbe.
  return {
    **coverage.to_dict(),
    'days': [day.to_dict() for day in sorted(coverage.days, key=lambda day: (day.day_of_week, day.start_time))],
  }


def get_coverage_dict(coverage_id: int) -> dict:
  with Session() as session:
    coverage = (
      session.query(DeliveryCoverage)
      .options(joinedload(DeliveryCoverage.days))
      .filter(DeliveryCoverage.id == coverage_id)
      .one()
    )
    return format_coverage(coverage)


def query_delivery_users() -> list[User]:
  with Session() as session:
    return session.query(User).filter(User.role == UserRole.DELIVERY).order_by(asc(User.nickname)).all()


def query_coverages() -> list[dict]:
  with Session() as session:
    coverages = (
      session.query(DeliveryCoverage)
      .options(joinedload(DeliveryCoverage.days))
      .order_by(desc(DeliveryCoverage.start_date))
      .all()
    )
    return [format_coverage(coverage) for coverage in coverages]


def query_coverage_day(coverage_id: int, day_of_week: int) -> DeliveryCoverageDay | None:
  with Session() as session:
    return (
      session.query(DeliveryCoverageDay)
      .filter(
        DeliveryCoverageDay.coverage_id == coverage_id,
        DeliveryCoverageDay.day_of_week == day_of_week,
      )
      .first()
    )


def query_absences() -> list[DeliveryAbsence]:
  with Session() as session:
    return session.query(DeliveryAbsence).order_by(desc(DeliveryAbsence.start_date)).all()

import json
from sqlalchemy import and_
from flask import Blueprint, request
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

from database_api import Session
from ..database.enum import UserRole
from . import flask_session_authentication
from database_api.operations import create, delete, get_by_id
from ..database.schema import GeographicZone, Constraint, GeographicCode, ItalcoUser, Order


geographic_zone_bp = Blueprint('geographic_zone_bp', __name__)

with open('static/caps.json', 'r') as file:
  CAPS_DATA: dict = json.load(file)


@geographic_zone_bp.route('', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def create_geographic_zone(user: ItalcoUser):
  return {'status': 'ok', 'geographic_zone': create(GeographicZone, request.json).to_dict()}


@geographic_zone_bp.route('<id>', methods=['DELETE'])
@flask_session_authentication([UserRole.ADMIN])
def delete_geographic_zone(user: ItalcoUser, id):
  delete(get_by_id(GeographicZone, int(id)))
  return {'status': 'ok', 'message': 'Operazione completata'}


@geographic_zone_bp.route('', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.CUSTOMER])
def get_geographic_zones(user: ItalcoUser):
  return {'status': 'ok', 'geographic_zones': execute_query_and_format_result()}


@geographic_zone_bp.route('<entity>', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def create_entity(user: ItalcoUser, entity: str):
  klass = get_class(entity)
  if klass == Constraint:
    if request.json['day_of_week'] not in list(range(7)):
      raise ValueError('Invalid day_of_week value')

  return {'status': 'ok', 'entity': create(klass, request.json).to_dict()}


@geographic_zone_bp.route('<entity>/<id>', methods=['DELETE'])
@flask_session_authentication([UserRole.ADMIN])
def delete_constraint(user: ItalcoUser, entity, id):
  delete(get_by_id(get_class(entity), int(id)))
  return {'status': 'ok', 'message': 'Operazione completata'}


def check_geographic_zone() -> list[datetime]:
  province = get_province_by_cap(request.json['cap'])
  caps = CAPS_DATA[province].copy() if province in CAPS_DATA else []
  for cap in query_special_caps_by_geographic_zone(province):
    if cap.type:
      caps.append(cap.code)
    else:
      caps.remove(cap.code)

  zones = execute_query_and_format_result(province)
  constraints = zones[0]['constraints'] if zones else []
  orders = get_orders_by_cap(caps)
  constraint_days = [constraint['day_of_week'] for constraint in constraints]
  start = datetime.today().date()
  allowed_dates = []
  end = start + relativedelta(months=2)
  while start <= end:
    if start.weekday() in constraint_days:
      order_count = 0
      for order in orders:
        if order.dpc == start:
          order_count += 1
      for rule in constraints:
        if rule['day_of_week'] == start.weekday() and order_count < rule['max_orders']:
          allowed_dates.append(start.strftime('%Y-%m-%d'))
          break
    start += timedelta(days=1)
  return allowed_dates


def execute_query_and_format_result(province=None) -> list[dict]:
  geographic_zones = []
  for tupla in query_geographic_zones(province):
    geographic_zones = format_query_result(tupla, geographic_zones)
  return geographic_zones


def get_class(entity: str):
  if entity == 'constraint':
    return Constraint
  elif entity == 'code':
    return GeographicCode
  else:
    raise ValueError(f'Unknown entity type: {entity}')


def query_geographic_zones(province=None) -> list[tuple[GeographicZone, Constraint, GeographicCode]]:
  with Session() as session:
    query = (
      session.query(GeographicZone, Constraint, GeographicCode)
      .outerjoin(Constraint, GeographicZone.id == Constraint.zone_id)
      .outerjoin(GeographicCode, GeographicZone.id == GeographicCode.zone_id)
    )
    if province:
      query = query.filter(GeographicZone.name == province)
    return query.all()


def format_query_result(tupla: tuple[GeographicZone, Constraint, GeographicCode], list: list[dict]) -> list[dict]:
  for element in list:
    if element['id'] == tupla[0].id:
      if tupla[2] and tupla[2].id not in [code['id'] for code in element['codes']]:
        element['codes'].append(tupla[2].to_dict())
      if tupla[1] and tupla[1].id not in [constraint['id'] for constraint in element['constraints']]:
        element['constraints'].append(tupla[1].to_dict())
      return list

  list.append(
    {
      **tupla[0].to_dict(),
      'codes': [tupla[2].to_dict()] if tupla[2] else [],
      'constraints': [tupla[1].to_dict()] if tupla[1] else [],
    }
  )
  return list


def get_province_by_cap(cap: str) -> str:
  for province, caps in CAPS_DATA.items():
    if cap in caps:
      return province
  raise ValueError(f'CAP {cap} not found in any province')


def query_special_caps_by_geographic_zone(province: str) -> list[GeographicCode]:
  with Session() as session:
    return (
      session.query(GeographicCode)
      .join(GeographicZone, and_(GeographicZone.id == GeographicCode.zone_id, GeographicZone.name == province))
      .all()
    )


def get_orders_by_cap(caps: list[str]) -> list[Order]:
  with Session() as session:
    return (
      session.query(Order)
      .filter(Order.cap.in_(caps), Order.dpc > datetime.today(), Order.dpc < datetime.today() + relativedelta(months=2))
      .all()
    )

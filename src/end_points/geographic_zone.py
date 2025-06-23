from flask import Blueprint, request

from database_api import Session
from ..database.enum import UserRole
from database_api.operations import create, delete, get_by_id
from . import error_catching_decorator, flask_session_authentication
from ..database.schema import GeographicZone, Constraint, GeographicCode, ItalcoUser


geographic_zone_bp = Blueprint('geographic_zone_bp', __name__)


@geographic_zone_bp.route('', methods=['POST'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN])
def create_geographic_zone(user: ItalcoUser):
  return {
    'status': 'ok',
    'geographic_zone': create(GeographicZone, request.json).to_dict()
  }


@geographic_zone_bp.route('<id>', methods=['DELETE'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN])
def delete_geographic_zone(user: ItalcoUser, id):
  delete(get_by_id(GeographicZone, int(id)))
  return {
    'status': 'ok',
    'message': 'Operazione completata'
  }


@geographic_zone_bp.route('', methods=['GET'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN])
def get_geographic_zones(user: ItalcoUser):
  geographic_zones = []
  for tupla in query_geographic_zones():
    geographic_zones = format_query_result(tupla, geographic_zones)

  return {
    'status': 'ok',
    'geographic_zones': geographic_zones
  }


@geographic_zone_bp.route('<entity>', methods=['POST'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN])
def create_entity(user: ItalcoUser, entity: str):
  return {
    'status': 'ok',
    'entity': create(get_class(entity), request.json).to_dict()
  }


@geographic_zone_bp.route('<entity>/<id>', methods=['DELETE'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN])
def delete_constraint(user: ItalcoUser, entity, id):
  delete(get_by_id(get_class(entity), int(id)))
  return {
    'status': 'ok',
    'message': 'Operazione completata'
  }


def get_class(entity: str):
  if entity == 'constraint':
    return Constraint
  elif entity == 'code':
    return GeographicCode
  else:
    raise ValueError(f'Unknown entity type: {entity}')


def query_geographic_zones() -> list[tuple[GeographicZone, Constraint, GeographicCode]]:
  with Session() as session:
    return session.query(
      GeographicZone, Constraint, GeographicCode
    ).outerjoin(
      Constraint, GeographicZone.id == Constraint.zone_id
    ).outerjoin(
      GeographicCode, GeographicZone.id == GeographicCode.zone_id
    ).all()


def format_query_result(tupla: tuple[GeographicZone, Constraint, GeographicCode], list: list[dict]) -> list[dict]:
  for element in list:
    if element['id'] == tupla[0].id:
      if tupla[2] and not tupla[2].id in [code['id'] for code in element['codes']]:
        element['codes'].append(tupla[2].to_dict())
      if tupla[1] and not tupla[1].id in [constraint['id'] for constraint in element['constraints']]:
        element['constraints'].append(tupla[1].to_dict())
      return list

  list.append({
    **tupla[0].to_dict(),
    'codes': [tupla[2].to_dict()] if tupla[2] else [],
    'constraints': [tupla[1].to_dict()] if tupla[1] else []
  })
  return list

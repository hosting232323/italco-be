from flask import Blueprint, request

from database_api import Session
from ..database.enum import UserRole
from ..database.schema import GeographicZone, Constraint, ItalcoUser
from . import error_catching_decorator, flask_session_authentication
from database_api.operations import create, delete, get_by_id, update, create_bulk, get_all


geographic_zone_bp = Blueprint('geographic_zone_bp', __name__)


@geographic_zone_bp.route('', methods=['POST'])
def create_geographic_zones():
  data = request.get_json()

  zone = create(GeographicZone, {
    "name": data["name"],
    "province": data["province"]
  })

  constraints_data = [
    {
      "zone_id": zone.id,
      "day_of_week": c["day_of_week"],
      "max_orders": c["max_orders"]
    }
    for c in data["constraints"]
  ]

  create_bulk(Constraint, constraints_data)
  
  return {
    "status": "ok",
    "message": "Zona e vincoli creati"
  }


@geographic_zone_bp.route('', methods=['GET'])
def get_geographic_zones():
  geographic_zones = []
  for tupla in query_geographic_zones():
    geographic_zones = format_query_result(tupla, geographic_zones)
    
  return {
    'status': 'ok',
    'geographic_zones': geographic_zones
  }


def query_geographic_zones() -> list[tuple[GeographicZone, Constraint]]:
  with Session() as session:
    return session.query(GeographicZone, Constraint).outerjoin(
      Constraint, GeographicZone.id == Constraint.zone_id
    ).all()


def format_query_result(tupla: tuple[GeographicZone, Constraint], list: list[dict]) -> list[dict]:
  for element in list:
    if element['id'] == tupla[0].id:
      element['constraint'].append(tupla[1].to_dict())
      return list
    
  list.append({
    **tupla[0].to_dict(),
    'constraint': [tupla[1].to_dict()]
  })
  return list
  
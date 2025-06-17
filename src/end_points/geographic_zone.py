from flask import Blueprint, request

from database_api import Session
from ..database.enum import UserRole
from ..database.schema import GeographicZone, Constraint
from . import error_catching_decorator, flask_session_authentication
from database_api.operations import create, delete, get_by_id, update, create_bulk


geographic_zone_bp = Blueprint('geographic_zone_bp', __name__)


@geographic_zone_bp.route('/', methods=['POST'])
def seed_geographic_zones():
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
    "message": "Zona e vincoli creati"
  }

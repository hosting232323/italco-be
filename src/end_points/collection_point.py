import logging

import requests
from sqlalchemy import and_, desc
from flask import Blueprint, request

from database_api import Session
from ..database.enum import UserRole
from . import flask_session_authentication
from database_api.operations import create, delete, get_by_id, update
from ..database.schema import CollectionPoint, User, ServiceUser, Product
from ..utils.caps import get_lat_lon_by_address


logger = logging.getLogger(__name__)

collection_point_bp = Blueprint('collection_point_bp', __name__)


def format_collection_point(collection_point: CollectionPoint) -> dict:
  # lat/lon non sono colonne salvate: si geocodifica l'indirizzo a ogni lettura, come
  # per i CAP disegnati sulla mappa in delivery_coverage.py (stessa cache di get_lat_lon_by_address).
  # None se il geocoding fallisce: il FE lo interpreta come "nessun marker per questo punto".
  # Vale anche se il geocoder e' giu': le coordinate servono solo alla mappa, e la stessa
  # lista alimenta la scelta del punto di ritiro nella creazione dell'ordine, che non deve
  # smettere di funzionare per un marker mancante.
  try:
    lat, lon = get_lat_lon_by_address(collection_point.address)
  except requests.RequestException as error:
    logger.warning('Geocoding del punto di ritiro %s non riuscito: %s', collection_point.id, error)
    lat, lon = None, None
  return {**collection_point.to_dict(), 'lat': lat, 'lon': lon}


@collection_point_bp.route('', methods=['POST'])
@flask_session_authentication([UserRole.CUSTOMER])
def create_collection_point(user: User):
  data = {**request.json, 'user_id': user.id}
  return {'status': 'ok', 'collection_point': create(CollectionPoint, data).to_dict()}


@collection_point_bp.route('<id>', methods=['DELETE'])
@flask_session_authentication([UserRole.CUSTOMER])
def delete_collection_point(_, id):
  delete(get_by_id(CollectionPoint, int(id)))
  return {'status': 'ok', 'message': 'Operazione completata'}


@collection_point_bp.route('', methods=['GET'])
@flask_session_authentication([UserRole.CUSTOMER, UserRole.OPERATOR, UserRole.ADMIN, UserRole.DELIVERY])
def get_collection_points(user: User):
  return {
    'status': 'ok',
    'collection_points': [format_collection_point(cp) for cp in query_collection_points(user)],
  }


@collection_point_bp.route('<id>', methods=['PUT'])
@flask_session_authentication([UserRole.CUSTOMER, UserRole.OPERATOR, UserRole.ADMIN])
def update_collection_point(_, id):
  collection_point: CollectionPoint = get_by_id(CollectionPoint, int(id))
  return {'status': 'ok', 'order': update(collection_point, request.json).to_dict()}


def query_collection_points(user: User) -> list[CollectionPoint]:
  with Session() as session:
    query = session.query(CollectionPoint)
    if user.role == UserRole.CUSTOMER:
      query = query.filter(CollectionPoint.user_id == user.id)
    return query.order_by(desc(CollectionPoint.created_at)).all()


def query_collection_points_available(order_id: int) -> list[CollectionPoint]:
  with Session() as session:
    return (
      session.query(CollectionPoint)
      .join(User, CollectionPoint.user_id == User.id)
      .join(ServiceUser, User.id == ServiceUser.user_id)
      .join(Product, and_(Product.service_user_id == ServiceUser.id, Product.order_id == order_id))
      .all()
    )

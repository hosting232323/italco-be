from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import and_, desc
from flask import Blueprint, request

from database_api import Session
from ..database.enum import UserRole
from . import flask_session_authentication
from database_api.operations import create, delete, get_by_id, update
from ..database.schema import CollectionPoint, User, ServiceUser, Product
from ..utils.caps import get_lat_lon_by_address


collection_point_bp = Blueprint('collection_point_bp', __name__)


def format_collection_point(collection_point: CollectionPoint) -> dict:
  # lat/lon sono salvati sul punto: None se non sono ancora stati risolti (il FE
  # lo interpreta come "nessun marker per questo punto").
  return {**collection_point.to_dict(), 'lat': collection_point.lat, 'lon': collection_point.lon}


def _coordinates(address: str) -> dict:
  lat, lon = get_lat_lon_by_address(address) if address else (None, None)
  return {'lat': lat, 'lon': lon}


def _client_fields(payload: dict) -> dict:
  # Le coordinate le decide il geocoder, non il client.
  return {key: value for key, value in payload.items() if key not in ('lat', 'lon')}


def backfill_coordinates(collection_points: list[CollectionPoint]) -> None:
  """Risolve e salva le coordinate dei punti che non le hanno ancora.

  Succede una volta sola per punto (quelli creati prima che si salvassero, o il
  cui geocoding era fallito): le letture successive non toccano il geocoder. Se
  non risponde il punto resta senza coordinate e ci si riprova alla lettura dopo,
  senza far fallire la lista: serve anche a scegliere il punto di ritiro
  nella creazione dell'ordine.
  """
  missing = [point for point in collection_points if point.lat is None or point.lon is None]
  if not missing:
    return

  with ThreadPoolExecutor(max_workers=min(10, len(missing))) as executor:
    resolved = list(executor.map(lambda point: _coordinates(point.address), missing))

  for point, coordinates in zip(missing, resolved):
    if coordinates['lat'] is None:
      continue
    update(point, coordinates)
    point.lat, point.lon = coordinates['lat'], coordinates['lon']


@collection_point_bp.route('', methods=['POST'])
@flask_session_authentication([UserRole.CUSTOMER])
def create_collection_point(user: User):
  data = {**_client_fields(request.json), 'user_id': user.id}
  if data.get('address'):
    data.update(_coordinates(data['address']))
  return {'status': 'ok', 'collection_point': create(CollectionPoint, data).to_dict()}


@collection_point_bp.route('<id>', methods=['DELETE'])
@flask_session_authentication([UserRole.CUSTOMER])
def delete_collection_point(_, id):
  delete(get_by_id(CollectionPoint, int(id)))
  return {'status': 'ok', 'message': 'Operazione completata'}


@collection_point_bp.route('', methods=['GET'])
@flask_session_authentication([UserRole.CUSTOMER, UserRole.OPERATOR, UserRole.ADMIN, UserRole.DELIVERY])
def get_collection_points(user: User):
  collection_points = query_collection_points(user)
  if not collection_points:
    return {'status': 'ok', 'collection_points': []}

  backfill_coordinates(collection_points)
  return {
    'status': 'ok',
    'collection_points': [format_collection_point(point) for point in collection_points],
  }


@collection_point_bp.route('<id>', methods=['PUT'])
@flask_session_authentication([UserRole.CUSTOMER, UserRole.OPERATOR, UserRole.ADMIN])
def update_collection_point(_, id):
  collection_point: CollectionPoint = get_by_id(CollectionPoint, int(id))
  data = _client_fields(request.json)
  if 'address' in data and data['address'] != collection_point.address:
    data.update(_coordinates(data['address']))
  return {'status': 'ok', 'order': update(collection_point, data).to_dict()}


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

from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import and_, desc
from flask import Blueprint, request

from database_api import Session
from ..database.enum import UserRole
from . import flask_session_authentication
from database_api.operations import create, delete, get_by_id, update
from ..database.schema import CollectionPoint, User, ServiceUser, Product
from ..utils.geo import parse_coordinates
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
  # Le coordinate passano da _client_coordinates, mai così come arrivano.
  return {key: value for key, value in payload.items() if key not in ('lat', 'lon')}


def _client_coordinates(payload: dict, collection_point: CollectionPoint = None) -> dict:
  """Le coordinate mandate dal client, se sono una posizione nuova e plausibile.

  Arrivano dal menu Google o dalla mappa della correzione indirizzo. Il form
  però rimanda il punto intero, coordinate salvate comprese: se l'indirizzo
  cambia e le coordinate sono ancora quelle salvate, sono del vecchio indirizzo
  e decide il geocoder. Vuoto se non c'è niente da prendere dal client.
  """
  lat, lon = parse_coordinates(payload.get('lat'), payload.get('lon'))
  if lat is None:
    return {}
  if collection_point is not None:
    moved = payload.get('address', collection_point.address) != collection_point.address
    if moved and (lat, lon) == (collection_point.lat, collection_point.lon):
      return {}
  return {'lat': lat, 'lon': lon}


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
@flask_session_authentication([UserRole.CUSTOMER, UserRole.OPERATOR, UserRole.ADMIN])
def create_collection_point(user: User):
  data = {**_client_fields(request.json)}
  # Il cliente crea solo per sé; operatore/admin lo creano per il cliente indicato.
  if user.role == UserRole.CUSTOMER or not data.get('user_id'):
    data['user_id'] = user.id
  coordinates = _client_coordinates(request.json)
  if coordinates:
    data.update(coordinates)
  elif data.get('address'):
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
  collection_points = query_collection_points(user, request.args.get('user_id', type=int))
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
  coordinates = _client_coordinates(request.json, collection_point)
  if coordinates:
    data.update(coordinates)
  elif 'address' in data and data['address'] != collection_point.address:
    data.update(_coordinates(data['address']))
  return {'status': 'ok', 'order': update(collection_point, data).to_dict()}


def query_collection_points(user: User, customer_id: int | None = None) -> list[CollectionPoint]:
  with Session() as session:
    query = session.query(CollectionPoint)
    if user.role == UserRole.CUSTOMER:
      query = query.filter(CollectionPoint.user_id == user.id)
    elif customer_id is not None:
      query = query.filter(CollectionPoint.user_id == customer_id)
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

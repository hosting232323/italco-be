import re

from flask import Blueprint, request

from database_api import Session
from database_api.operations import create, delete, get_by_id, update

from ..database.enum import UserRole
from ..database.schema import CollectionPoint, PickupPoint, User
from ..utils.caps import get_lat_lon_by_address
from ..utils.geo import parse_coordinates
from . import flask_session_authentication


pickup_point_bp = Blueprint('pickup_point_bp', __name__)

# Ciò che il catalogo condivide con i punti dei clienti collegati.
SHARED_FIELDS = ('address', 'cap', 'lat', 'lon')


def address_key(address: str, cap: str) -> tuple[str, str]:
  """Chiave di confronto fra indirizzi: parole ordinate, senza punteggiatura né maiuscole.

  "Via X, 99" e "99 via x" sono lo stesso indirizzo.
  """
  words = sorted(re.sub(r'[\W_]+', ' ', (address or '').lower()).split())
  return ' '.join(words), (cap or '').strip()


def find_pickup_point(address: str, cap: str) -> PickupPoint | None:
  key = address_key(address, cap)
  with Session() as session:
    for pickup_point in session.query(PickupPoint).order_by(PickupPoint.id).all():
      if address_key(pickup_point.address, pickup_point.cap) == key:
        return pickup_point
  return None


def get_or_create_pickup_point(name: str, address: str, cap: str, lat=None, lon=None) -> PickupPoint:
  """La voce del catalogo con quell'indirizzo, creandola se non esiste.

  È ciò che unifica i duplicati: un punto "personale" con un indirizzo già
  presente finisce sulla stessa voce invece di aprirne un'altra.
  """
  existing = find_pickup_point(address, cap)
  if existing:
    if existing.lat is None and lat is not None:
      update(existing, {'lat': lat, 'lon': lon})
    return existing
  return create(PickupPoint, {'name': name, 'address': address, 'cap': cap, 'lat': lat, 'lon': lon})


def sync_collection_points(pickup_point: PickupPoint) -> None:
  """Allinea indirizzo, CAP e coordinate dei punti dei clienti collegati."""
  with Session() as session:
    points = session.query(CollectionPoint).filter(CollectionPoint.pickup_point_id == pickup_point.id).all()
  for point in points:
    update(point, {field: getattr(pickup_point, field) for field in SHARED_FIELDS})


def format_pickup_point(pickup_point: PickupPoint, points: list[CollectionPoint], customers: dict[int, User]) -> dict:
  return {
    **pickup_point.to_dict(),
    'customers': [
      {'id': point.user_id, 'nickname': customers[point.user_id].nickname, 'collection_point_id': point.id}
      for point in points
      if point.user_id in customers
    ],
  }


@pickup_point_bp.route('', methods=['GET'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN])
def get_pickup_points(_):
  with Session() as session:
    pickup_points = session.query(PickupPoint).order_by(PickupPoint.name, PickupPoint.id).all()
    points = session.query(CollectionPoint).filter(CollectionPoint.pickup_point_id.isnot(None)).all()
    customers = {user.id: user for user in session.query(User).filter(User.id.in_({p.user_id for p in points})).all()}
  by_pickup_point: dict[int, list[CollectionPoint]] = {}
  for point in points:
    by_pickup_point.setdefault(point.pickup_point_id, []).append(point)
  return {
    'status': 'ok',
    'pickup_points': [
      format_pickup_point(pickup_point, by_pickup_point.get(pickup_point.id, []), customers)
      for pickup_point in pickup_points
    ],
  }


def _fields(payload: dict) -> dict | None:
  name = str(payload.get('name') or '').strip()
  address = str(payload.get('address') or '').strip()
  cap = str(payload.get('cap') or '').strip()
  if not (name and address and cap):
    return None
  return {'name': name, 'address': address, 'cap': cap}


def _coordinates(payload: dict, fields: dict, current: PickupPoint = None) -> dict:
  lat, lon = parse_coordinates(payload.get('lat'), payload.get('lon'))
  moved = current is not None and (fields['address'], fields['cap']) != (current.address, current.cap)
  if lat is not None and not (moved and (lat, lon) == (current.lat, current.lon)):
    return {'lat': lat, 'lon': lon}
  if current is not None and not moved:
    return {}
  lat, lon = get_lat_lon_by_address(fields['address'], fields['cap'])
  return {'lat': lat, 'lon': lon}


def _duplicate(fields: dict, own_id: int = None) -> PickupPoint | None:
  found = find_pickup_point(fields['address'], fields['cap'])
  return found if found and found.id != own_id else None


@pickup_point_bp.route('', methods=['POST'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN])
def create_pickup_point(_):
  fields = _fields(request.json)
  if fields is None:
    return {'status': 'ko', 'message': 'Nome, indirizzo e CAP sono obbligatori'}
  if _duplicate(fields):
    return {'status': 'ko', 'message': 'Esiste già un punto di ritiro con questo indirizzo'}
  pickup_point = create(PickupPoint, {**fields, **_coordinates(request.json, fields)})
  return {'status': 'ok', 'pickup_point': pickup_point.to_dict()}


@pickup_point_bp.route('<id>', methods=['PUT'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN])
def update_pickup_point(_, id):
  pickup_point = get_by_id(PickupPoint, int(id))
  if not pickup_point:
    return {'status': 'ko', 'message': 'Punto di ritiro non trovato'}
  fields = _fields(request.json)
  if fields is None:
    return {'status': 'ko', 'message': 'Nome, indirizzo e CAP sono obbligatori'}
  if _duplicate(fields, pickup_point.id):
    return {'status': 'ko', 'message': 'Esiste già un punto di ritiro con questo indirizzo: usa Unisci'}
  pickup_point = update(pickup_point, {**fields, **_coordinates(request.json, fields, pickup_point)})
  sync_collection_points(pickup_point)
  return {'status': 'ok', 'pickup_point': pickup_point.to_dict()}


@pickup_point_bp.route('<id>', methods=['DELETE'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN])
def delete_pickup_point(_, id):
  pickup_point = get_by_id(PickupPoint, int(id))
  if not pickup_point:
    return {'status': 'ko', 'message': 'Punto di ritiro non trovato'}
  with Session() as session:
    used = session.query(CollectionPoint.id).filter(CollectionPoint.pickup_point_id == pickup_point.id).count()
  if used:
    return {'status': 'ko', 'message': f'Impossibile eliminare: usato da {used} punti di ritiro dei clienti'}
  delete(pickup_point)
  return {'status': 'ok', 'message': 'Operazione completata'}


@pickup_point_bp.route('merge', methods=['POST'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN])
def merge_pickup_points(_):
  """Unisce più voci in una: i punti dei clienti passano alla voce di destinazione."""
  target = get_by_id(PickupPoint, int(request.json.get('target_id') or 0))
  if not target:
    return {'status': 'ko', 'message': 'Punto di ritiro non trovato'}
  source_ids = {int(source_id) for source_id in request.json.get('source_ids') or []} - {target.id}
  if not source_ids:
    return {'status': 'ko', 'message': 'Seleziona almeno una voce da unire'}
  with Session() as session:
    sources = session.query(PickupPoint).filter(PickupPoint.id.in_(source_ids)).all()
    if len(sources) != len(source_ids):
      return {'status': 'ko', 'message': 'Punto di ritiro non trovato'}
    # Update diretto: caricare i punti e poi cancellare la voce farebbe azzerare loro il pickup_point_id.
    session.query(CollectionPoint).filter(CollectionPoint.pickup_point_id.in_(source_ids)).update(
      {'pickup_point_id': target.id, **{field: getattr(target, field) for field in SHARED_FIELDS}},
      synchronize_session=False,
    )
    for source in sources:
      session.delete(source)
    session.commit()
  return {'status': 'ok', 'message': 'Operazione completata'}

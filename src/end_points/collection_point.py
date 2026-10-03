from sqlalchemy import and_, desc
from flask import Blueprint, request

from database_api import Session
from ..database.enum import UserRole
from . import flask_session_authentication
from database_api.operations import create, delete, get_by_id, update
from ..database.schema import CollectionPoint, User, ServiceUser, Product


collection_point_bp = Blueprint('collection_point_bp', __name__)


@collection_point_bp.route('', methods=['POST'])
@flask_session_authentication([UserRole.CUSTOMER, UserRole.OPERATOR, UserRole.ADMIN])
def create_collection_point(user: User):
  data = {**request.json}
  # Il cliente crea solo per sé; operatore/admin lo creano per il cliente indicato.
  if user.role == UserRole.CUSTOMER or not data.get('user_id'):
    data['user_id'] = user.id
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
  return {'status': 'ok', 'collection_points': [collection_point.to_dict() for collection_point in collection_points]}


@collection_point_bp.route('<id>', methods=['PUT'])
@flask_session_authentication([UserRole.CUSTOMER, UserRole.OPERATOR, UserRole.ADMIN])
def update_collection_point(_, id):
  collection_point: CollectionPoint = get_by_id(CollectionPoint, int(id))
  return {'status': 'ok', 'order': update(collection_point, request.json).to_dict()}


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

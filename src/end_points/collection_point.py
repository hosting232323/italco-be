from flask import Blueprint, request

from database_api import Session
from ..database.enum import UserRole
from ..database.schema import CollectionPoint, ItalcoUser
from database_api.operations import create, delete, get_by_id
from . import error_catching_decorator, flask_session_authentication


collection_point_bp = Blueprint('collection_point_bp', __name__)


@collection_point_bp.route('', methods=['POST'])
@error_catching_decorator
@flask_session_authentication([UserRole.CUSTOMER])
def create_collection_point(user: ItalcoUser):
  request.json['user_id'] = user.id
  return {
    'status': 'ok',
    'collection_point': create(CollectionPoint, request.json).to_dict()
  }


@collection_point_bp.route('<id>', methods=['DELETE'])
@error_catching_decorator
@flask_session_authentication([UserRole.CUSTOMER])
def delete_collection_point(user: ItalcoUser, id):
  delete(get_by_id(CollectionPoint, int(id)))
  return {
    'status': 'ok',
    'message': 'Operazione completata'
  }


@collection_point_bp.route('', methods=['GET'])
@error_catching_decorator
@flask_session_authentication([UserRole.CUSTOMER, UserRole.OPERATOR, UserRole.ADMIN, UserRole.DELIVERY])
def get_collection_points(user: ItalcoUser):
  return {
    'status': 'ok',
    'collection_points': [
      collection_point.to_dict() for collection_point in query_collection_points(user)
    ]
  }


def query_collection_points(user: ItalcoUser) -> list[CollectionPoint]:
  with Session() as session:
    query = session.query(CollectionPoint)
    if user.role == UserRole.CUSTOMER:
      query = query.filter(
        CollectionPoint.user_id == user.id
      )
    return query.all()

from flask import Blueprint, request
from ..database.enum import UserRole
from .users.session import flask_session_authentication
from ..database.schema import User, Log
from database_api import Session


log_bp = Blueprint('log_bp', __name__)


@log_bp.route('', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def get_logs(user: User):
  return {
    'status': 'ok', 
    'logs': [{'logs': log.to_dict(), 'user': user.to_dict()} for log, user in query_logs(request.json['filters'])]
  }


def query_logs(filters: list) -> list[tuple[Log, User]]:
  with Session() as session:
    query = (
      session.query(Log, User)
      .join(User, Log.user_id == User.id)
    )
    
    for filter in filters:
      model = globals()[filter['model']]
      field = getattr(model, filter['field'])
      value = filter['value']
      
      if model == User:
        query = query.filter(field == value)
      
    query = query.order_by(Log.created_at.desc())
    query = query.limit(300)
    return query.all()

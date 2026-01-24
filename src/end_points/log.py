from flask import Blueprint
from ..database.enum import UserRole
from .users.session import flask_session_authentication
from ..database.schema import User, Log
from database_api import Session


log_bp = Blueprint('log_bp', __name__)


@log_bp.route('', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN])
def get_logs(user: User):
  return {
    'status': 'ok', 
    'data': [log.to_dict() for log in query_logs()]
  }

def query_logs() -> list[Log]:
  with Session() as session:
    return (
      session.query(Log)
      .order_by(Log.created_at.desc())
      .limit(300)
      .all()
    )

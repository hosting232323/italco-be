from flask import Blueprint
from ..database.enum import UserRole
from .users.session import flask_session_authentication
from ..database.schema import User, Log
from database_api import Session


log_bp = Blueprint('log_bp', __name__)


@log_bp.route('', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN])
def get_logs(user: User):
  return {'status': 'ok', 'logs': [{'logs': log.to_dict(), 'user': user.to_dict()} for log, user in query_logs()]}


def query_logs() -> list[tuple[Log, User]]:
  with Session() as session:
    return session.query(Log, User).join(User, Log.user_id == User.id).order_by(Log.created_at.desc()).limit(300).all()

from flask import Blueprint
from ..database.enum import UserRole
from .users.session import flask_session_authentication
from ..database.schema import User, Log
from database_api import Session


log_bp = Blueprint('log_bp', __name__)


@log_bp.route('', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN])
def get_logs(user: User):
  print(query_logs())
  logs = []
  for tupla in query_logs():
    logs = format_query_logs(tupla, logs)
  return {
    'status': 'ok', 
    'data': logs
  }


def query_logs() -> list[Log]:
  with Session() as session:
    return (
      session.query(Log, User)
      .outerjoin(User, Log.user_id == User.id)
      .order_by(Log.created_at.desc())
      .limit(300)
      .all()
    )


def format_query_logs(
  tupla: tuple[Log, User],
  list: list[dict]
) -> list[dict]:
  for element in list:
    print(element)
  
  output = {
    **tupla[0].to_dict(),
    'user': tupla[1].format_user()
  }
    
  return list

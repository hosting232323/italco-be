from sqlalchemy import cast, Date
from flask import Blueprint, request

from sqlalchemy.orm import defer
from database_api import Session
from ..utils.date import handle_date
from ..database.enum import UserRole
from ..database.schema import User, Log
from database_api.operations import get_by_id
from .users.session import flask_session_authentication


log_bp = Blueprint('log_bp', __name__)


@log_bp.route('', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def get_logs(user: User):
  return {
    'status': 'ok',
    'logs': [{'logs': log.to_dict(), 'user': user.to_dict()} for log, user in query_logs(request.json['filters'])],
  }


@log_bp.route('', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN])
def get_log(user: User):
  return {
    'status': 'ok',
    'log': get_by_id(Log, request.args.get('log_id')).to_dict(),
  }


def query_logs(filters: list) -> list[tuple[Log, User]]:
  with Session() as session:
    query = session.query(Log, User).join(User, Log.user_id == User.id).options(defer(Log.content))

    for filter in filters:
      model = globals()[filter['model']]
      field = getattr(model, filter['field'])
      value = filter['value']

      if model == Log and type(value) is list and field == Log.created_at:
        query = query.filter(field >= handle_date(value[0]), field <= handle_date(value[1]))
      elif model == Log and field == Log.created_at:
        query = query.filter(cast(field, Date) == value)
      else:
        query = query.filter(field == value)

    query = query.order_by(Log.created_at.desc())
    query = query.limit(300)
    return query.all()

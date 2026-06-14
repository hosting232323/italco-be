from flask import Blueprint, request

from ...database.enum import UserRole
from .queries import query_logs, find_log, format_log
from ..users.session import flask_session_authentication


log_bp = Blueprint('log_bp', __name__)


@log_bp.route('filter', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def get_logs(_):
  return {
    'status': 'ok',
    'logs': [
      {'logs': entry, 'user': {'id': entry['user_id'], 'nickname': entry['nickname']}}
      for entry in query_logs(request.json['filters'])
    ],
  }


@log_bp.route('<log_id>', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN])
def get_log(_, log_id):
  entry = find_log(log_id)
  if not entry:
    return {'status': 'ko', 'error': 'Log non trovato'}

  return {'status': 'ok', 'log': format_log(entry)}

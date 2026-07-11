from flask import Blueprint, request

from .. import STATIC_FOLDER
from ..database.enum import UserRole
from api.log import query_logs, find_log, format_log
from . import flask_session_authentication


log_bp = Blueprint('log_bp', __name__)


@log_bp.route('filter', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def get_logs(_):
  return {
    'status': 'ok',
    'logs': [
      {'logs': entry, 'user': {'id': entry['user_id'], 'identifier': entry['identifier']}}
      for entry in query_logs(request.json['filters'], STATIC_FOLDER)
    ],
  }


@log_bp.route('<log_id>', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN])
def get_log(_, log_id):
  entry = find_log(log_id, STATIC_FOLDER)
  if not entry:
    return {'status': 'ko', 'message': 'Log non trovato'}

  return {'status': 'ok', 'log': format_log(entry)}

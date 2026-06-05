import json
from pathlib import Path
from flask import Blueprint, request

from .. import STATIC_FOLDER, IS_DEV
from database_api import Session
from ..database.enum import UserRole
from ..database.schema import User
from .users.session import flask_session_authentication


log_bp = Blueprint('log_bp', __name__)
LOG_DIR = Path(STATIC_FOLDER) / ('test' if IS_DEV else 'prod') / 'logs'


@log_bp.route('filter', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def get_logs(_):
  return {
    'status': 'ok',
    'logs': [{'logs': entry, 'user': get_user(entry['user_id'])} for entry in query_logs(request.json['filters'])],
  }


@log_bp.route('', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN])
def get_log(_):
  # TODO: ID nell'url
  log_id = request.args.get('log_id')

  for entry in iter_logs():
    if entry['ts'] == log_id:
      return {
        'status': 'ok',
        'log': {
          'id': entry['ts'],
          'created_at': entry['ts'],
          'content': json.dumps(
            {
              'request': entry['request'],
              'response': entry['response'],
            }
          ),
        },
      }

  return {'status': 'ko', 'error': 'Log non trovato'}


def query_logs(filters: list) -> list:
  def get(model, field):
    f = next((f for f in filters if f.get('model') == model and f.get('field') == field), None)
    return f['value'] if f else None

  date = get('Log', 'created_at')
  user_id = get('User', 'id')
  status = get('Log', 'status')

  date_range = None
  for f in filters:
    if f.get('model') == 'Log' and f.get('field') == 'created_at' and isinstance(f['value'], list):
      date_range = f['value']
      date = None
      break

  results = []
  for entry in iter_logs(date=date, date_range=date_range, user_id=user_id, status=status):
    results.append(
      {
        'id': entry['ts'],
        'created_at': entry['ts'],
        'content': json.dumps(
          {
            'request': entry['request'],
            'response': entry['response'],
          }
        ),
        'user_id': entry['user_id'],
        'nickname': entry['nickname'],
      }
    )
  return results


def iter_logs(date=None, date_range=None, user_id=None, status=None, limit=300):
  files = sorted(LOG_DIR.glob('*.jsonl'), reverse=True)

  if date:
    files = [f for f in files if f.stem == date]
  elif date_range:
    start, end = date_range[0][:10], date_range[1][:10]
    files = [f for f in files if start <= f.stem <= end]

  count = 0
  for file in files:
    with open(file, encoding='utf-8') as f:
      lines = f.readlines()
    for line in reversed(lines):
      entry = json.loads(line)
      if user_id and entry['user_id'] != user_id:
        continue
      if status and entry.get('response', {}).get('status') != status:
        continue
      yield entry
      count += 1
      if count >= limit:
        return


def get_user(user_id: int) -> dict:
  with Session() as session:
    user = session.query(User).get(user_id)
    return user.to_dict() if user else {}

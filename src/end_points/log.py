import json
from pathlib import Path
from datetime import datetime
from flask import Blueprint, request

from .. import STATIC_FOLDER, IS_DEV
from ..database.enum import UserRole
from .users.session import flask_session_authentication, ROME_TZ


LOG_MAX_LINE_BYTES = 1_000_000
log_bp = Blueprint('log_bp', __name__)
LOG_DIR = Path(STATIC_FOLDER) / ('test' if IS_DEV else 'prod') / 'logs'


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

  request_info = entry.get('request') or {}
  return {
    'status': 'ok',
    'log': {
      'id': entry['ts'],
      'created_at': entry['ts'],
      'method': request_info.get('method'),
      'endpoint': request_info.get('path'),
      'content': json.dumps({'request': entry['request'], 'response': entry['response']}),
    },
  }


def query_logs(filters: list) -> list:
  def get(model, field):
    f = next((f for f in filters if f.get('model') == model and f.get('field') == field), None)
    return f['value'] if f else None

  user_id = get('User', 'id')
  status = get('Log', 'status')
  start, end = parse_date_filter(get('Log', 'created_at'))

  results = []
  for entry in iter_logs(start=start, end=end, user_id=user_id, status=status):
    request_info = entry.get('request') or {}
    results.append(
      {
        'id': entry['ts'],
        'created_at': entry['ts'],
        'method': request_info.get('method'),
        'endpoint': request_info.get('path'),
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


def iter_logs(start=None, end=None, user_id=None, status=None, limit=300):
  files = sorted(LOG_DIR.glob('*/*.jsonl'), reverse=True)

  if start or end:
    start_day = start.strftime('%Y-%m-%d') if start else None
    end_day = end.strftime('%Y-%m-%d') if end else None
    files = [f for f in files if (start_day is None or f.stem >= start_day) and (end_day is None or f.stem <= end_day)]

  count = 0
  for file in files:
    for entry in reversed(read_entries(file)):
      if user_id and entry['user_id'] != user_id:
        continue
      if status and (entry.get('response') or {}).get('status') != status:
        continue
      if (start or end) and not _in_range(entry['ts'], start, end):
        continue
      yield entry
      count += 1
      if count >= limit:
        return


def find_log(log_id: str) -> dict | None:
  log_file = LOG_DIR / log_id[:7] / f'{log_id[:10]}.jsonl'
  if not log_file.exists():
    return None

  for entry in read_entries(log_file):
    if entry.get('ts') == log_id:
      return entry
  return None


def read_entries(file) -> list:
  entries = []
  with open(file, encoding='utf-8') as f:
    while True:
      part = f.readline(LOG_MAX_LINE_BYTES + 1)
      if not part:
        break
      if not part.endswith('\n') and len(part) > LOG_MAX_LINE_BYTES:
        while True:
          more = f.readline(LOG_MAX_LINE_BYTES + 1)
          if not more or more.endswith('\n'):
            break
        continue
      line = part.strip()
      if not line:
        continue
      try:
        entries.append(json.loads(line))
      except json.JSONDecodeError:
        continue
  return entries


def parse_date_filter(value) -> tuple:
  if not value:
    return None, None

  if isinstance(value, list):
    start = _to_bound(value[0], end=False) if len(value) > 0 and value[0] else None
    end = _to_bound(value[1], end=True) if len(value) > 1 and value[1] else None
    return start, end

  return _to_bound(value, end=False), _to_bound(value[:10], end=True)


def _to_bound(value: str, end: bool) -> datetime:
  dt = datetime.fromisoformat(value)
  if end and _is_date_only(value):
    dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
  return ROME_TZ.localize(dt) if dt.tzinfo is None else dt


def _is_date_only(value: str) -> bool:
  return 'T' not in value and ' ' not in value


def _in_range(ts: str, start, end) -> bool:
  dt = datetime.fromisoformat(ts)
  if start and dt < start:
    return False
  if end and dt > end:
    return False
  return True

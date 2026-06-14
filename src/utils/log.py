import json
import decimal
from pathlib import Path
from datetime import datetime

from .. import STATIC_FOLDER, IS_DEV
from .date import ROME_TZ
from api.telegram import extract_request_data


LOG_DIR = Path(STATIC_FOLDER) / ('test' if IS_DEV else 'prod') / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOG_MAX_FIELD_CHARS = 50_000
LOG_MAX_LINE_BYTES = 1_000_000


def write_log(user, response=None):
  request_info = extract_request_data(False)
  request_info.pop('headers', None)

  now = datetime.now(ROME_TZ)
  month_dir = LOG_DIR / now.strftime('%Y-%m')
  month_dir.mkdir(parents=True, exist_ok=True)
  log_file = month_dir / f'{now.strftime("%Y-%m-%d")}.jsonl'
  line = json.dumps(
    {
      'ts': now.isoformat(),
      'user_id': user.id,
      'nickname': user.nickname,
      'request': _cap_request(request_info),
      'response': _cap_field(response),
    },
    ensure_ascii=False,
    default=_log_default,
  )

  with open(log_file, 'a', encoding='utf-8') as file:
    file.write(line)
    file.write('\n')


def iter_entries_reversed(file, block_size=65536):
  with open(file, 'rb') as f:
    f.seek(0, 2)
    pos = f.tell()
    pending = b''
    while pos > 0:
      read_size = min(block_size, pos)
      pos -= read_size
      f.seek(pos)
      pending = f.read(read_size) + pending

      newline = pending.rfind(b'\n')
      while newline != -1:
        entry = _parse_line(pending[newline + 1:])
        pending = pending[:newline]
        if entry is not None:
          yield entry
        newline = pending.rfind(b'\n')

      if len(pending) > LOG_MAX_LINE_BYTES:
        pending = b''

  entry = _parse_line(pending)
  if entry is not None:
    yield entry


def query_logs(filters: list) -> list:
  def get(model, field):
    f = next((f for f in filters if f.get('model') == model and f.get('field') == field), None)
    return f['value'] if f else None

  user_id = get('User', 'id')
  status = get('Log', 'status')
  start, end = parse_date_filter(get('Log', 'created_at'))

  return [
    {**format_log(entry), 'user_id': entry['user_id'], 'nickname': entry['nickname']}
    for entry in iter_logs(start=start, end=end, user_id=user_id, status=status)
  ]


def find_log(log_id: str) -> dict | None:
  log_file = LOG_DIR / log_id[:7] / f'{log_id[:10]}.jsonl'
  if not log_file.exists():
    return None

  for entry in iter_entries_reversed(log_file):
    if entry.get('ts') == log_id:
      return entry

  return None


def format_log(entry: dict) -> dict:
  request_info = entry.get('request') or {}
  return {
    'id': entry['ts'],
    'created_at': entry['ts'],
    'method': request_info.get('method'),
    'endpoint': request_info.get('path'),
    'content': json.dumps({'request': entry.get('request'), 'response': entry.get('response')}),
  }


def iter_logs(start=None, end=None, user_id=None, status=None, limit=100):
  files = sorted(LOG_DIR.glob('*/*.jsonl'), reverse=True)

  if start or end:
    start_day = start.strftime('%Y-%m-%d') if start else None
    end_day = end.strftime('%Y-%m-%d') if end else None
    files = [f for f in files if (start_day is None or f.stem >= start_day) and (end_day is None or f.stem <= end_day)]

  count = 0
  for file in files:
    for entry in iter_entries_reversed(file):
      if user_id and entry.get('user_id') != user_id:
        continue
      if status and (entry.get('response') or {}).get('status') != status:
        continue
      if (start or end) and not _in_range(entry.get('ts', ''), start, end):
        continue
      yield entry

      count += 1
      if count >= limit:
        return


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


def _parse_line(raw: bytes):
  raw = raw.strip()
  if not raw or len(raw) > LOG_MAX_LINE_BYTES:
    return None
  try:
    return json.loads(raw)
  except (json.JSONDecodeError, ValueError):
    return None


def _log_default(o):
  return float(o) if isinstance(o, decimal.Decimal) else str(o)


def _cap_request(request_info):
  if not isinstance(request_info, dict):
    return _cap_field(request_info)

  return {key: value if key in ('method', 'path') else _cap_field(value) for key, value in request_info.items()}


def _cap_field(value):
  if value is None:
    return None

  try:
    dumped = json.dumps(value, ensure_ascii=False, default=_log_default)
  except Exception:
    return {'_truncated': True, 'error': 'non serializzabile'}

  if len(dumped) <= LOG_MAX_FIELD_CHARS:
    return value

  return {'_truncated': True, 'chars': len(dumped), 'preview': dumped[:2000]}

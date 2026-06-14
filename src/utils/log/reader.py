import json

from .paths import LOG_DIR
from .dates import parse_date_filter, in_range
from .index import ensure_index, read_index, read_entry


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

  idx = ensure_index(log_file)
  for rec in read_index(idx):
    if rec.get('ts') == log_id:
      entry = read_entry(log_file, rec['off'])
      if entry is not None and entry.get('ts') == log_id:
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
    idx = ensure_index(file)
    for rec in reversed(read_index(idx)):
      if user_id and rec.get('user_id') != user_id:
        continue
      if status and rec.get('status') != status:
        continue
      if (start or end) and not in_range(rec.get('ts', ''), start, end):
        continue

      entry = read_entry(file, rec['off'])
      if entry is None:
        continue
      yield entry

      count += 1
      if count >= limit:
        return

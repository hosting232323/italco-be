import json
import decimal
from pathlib import Path
from datetime import datetime

from ... import STATIC_FOLDER, IS_DEV
from ...utils.date import ROME_TZ
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

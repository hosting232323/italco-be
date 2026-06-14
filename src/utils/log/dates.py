from datetime import datetime

from ..date import ROME_TZ


def parse_date_filter(value) -> tuple:
  if not value:
    return None, None

  if isinstance(value, list):
    start = _to_bound(value[0], end=False) if len(value) > 0 and value[0] else None
    end = _to_bound(value[1], end=True) if len(value) > 1 and value[1] else None
    return start, end

  return _to_bound(value, end=False), _to_bound(value[:10], end=True)


def in_range(ts: str, start, end) -> bool:
  dt = datetime.fromisoformat(ts)
  if start and dt < start:
    return False

  if end and dt > end:
    return False

  return True


def _to_bound(value: str, end: bool) -> datetime:
  dt = datetime.fromisoformat(value)
  if end and _is_date_only(value):
    dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
  return ROME_TZ.localize(dt) if dt.tzinfo is None else dt


def _is_date_only(value: str) -> bool:
  return 'T' not in value and ' ' not in value

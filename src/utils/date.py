import pytz
from datetime import datetime, date


ROME_TZ = pytz.timezone('Europe/Rome')


def handle_date(date_str: str | date) -> datetime:
  return date_str if isinstance(date_str, date) else datetime.strptime(date_str, '%Y-%m-%d')

from datetime import datetime, date


def handle_date(date_str: str | date) -> datetime:
  return date_str if isinstance(date_str, date) else datetime.strptime(date_str, '%Y-%m-%d')

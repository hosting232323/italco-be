from datetime import datetime

from .queries import get_all_histories_by_order_id


def get_statuses_by_order_id(order_id: int):
  statuses = []
  for history in get_all_histories_by_order_id(order_id):
    record = history.to_dict()
    if history.status['type'] == 'status':
      record['status'] = history.status['value']
    else:
      record[history.status['type']] = history.status.get('value')
      del record['status']
    statuses.append(record)

  return {'status': 'ok', 'statuses': statuses}


def parse_time(value: str) -> datetime.time:
  for fmt in ['%H:%M', '%H:%M:%S']:
    try:
      return datetime.strptime(value, fmt).time()
    except ValueError:
      continue

  raise ValueError(f'Formato orario non riconosciuto: {value}')

from datetime import datetime

from ...database.enum import OrderStatus
from .queries import get_all_histories_by_order_id


def get_statuses_by_order_id(order_id: int):
  status_map = {status.name: status.value for status in OrderStatus}
  statuses = []
  for history in get_all_histories_by_order_id(order_id):
    record = {
      'id': history.id,
      'order_id': history.order_id,
      'created_at': history.created_at.strftime('%d/%m/%Y %H:%M'),
      'updated_at': history.updated_at.strftime('%d/%m/%Y %H:%M'),
    }
    if history.status.get('type') == 'status':
      record['status'] = status_map.get(history.status['value'], history.status['value'])
    else:
      record[history.status['type']] = history.status.get('value')
    statuses.append(record)

  return {'status': 'ok', 'statuses': statuses}


def parse_time(value: str) -> datetime.time:
  for fmt in ['%H:%M', '%H:%M:%S']:
    try:
      return datetime.strptime(value, fmt).time()
    except ValueError:
      continue

  raise ValueError(f'Formato orario non riconosciuto: {value}')

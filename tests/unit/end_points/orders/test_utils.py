from datetime import time

import pytest

from database_api.operations import update

from src.database.enum import OrderStatus
from src.end_points.orders.utils import get_statuses_by_order_id, parse_time

from tests.unit.factories import create_order


def test_parse_time_short_format():
  assert parse_time('08:30') == time(8, 30)


def test_parse_time_with_seconds():
  assert parse_time('08:30:15') == time(8, 30, 15)


def test_parse_time_rejects_invalid_value():
  with pytest.raises(ValueError, match='Formato orario non riconosciuto'):
    parse_time('8.30')


def test_get_statuses_by_order_id_formats_status_records(db):
  order = create_order(status=OrderStatus.ACQUIRED)
  update(order, {'status': OrderStatus.BOOKED})

  result = get_statuses_by_order_id(order.id)

  assert result['status'] == 'ok'
  status_values = [record['status'] for record in result['statuses'] if 'status' in record]
  assert status_values == ['Acquired', 'Booked']


def test_get_statuses_by_order_id_formats_flag_records(db):
  order = create_order()
  update(order, {'anomaly': True})

  result = get_statuses_by_order_id(order.id)

  flag_records = [record for record in result['statuses'] if 'anomaly' in record]
  assert len(flag_records) == 1
  assert flag_records[0]['anomaly'] is True
  assert 'status' not in flag_records[0]

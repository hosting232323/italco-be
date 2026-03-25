from datetime import date

from src.database.enum import UserRole
from tests.utils import auth_header_for


def test_order_filter_returns_twenty_booked_orders_for_today(client):
  response = client.post('/order/filter', json={'filters': []}, headers=auth_header_for('admin', role=UserRole.ADMIN))

  assert response.status_code == 200
  body = response.get_json()
  assert body['status'] == 'ok'
  assert 'new_token' in body
  assert len(body['orders']) == 20
  assert all(order['status'] == 'Booked' for order in body['orders'])
  assert all(order['booking_date'] == date.today().isoformat() for order in body['orders'])


def test_order_filter_returns_only_cap_70020(client):
  response = client.post('/order/filter', json={'filters': []}, headers=auth_header_for('admin', role=UserRole.ADMIN))

  assert response.status_code == 200
  body = response.get_json()
  assert body['status'] == 'ok'
  assert all(order['cap'] == '70020' for order in body['orders'])

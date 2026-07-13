from datetime import date

from api import hooks, register_flask_hooks
from database_api import Session

import src.end_points.orders as orders_module
from src.database.enum import UserRole
from src.database.schema import Order
from src.end_points.orders.services import RaeProductDeletionError
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


def test_update_order_uses_base_hook_for_rae_product_deletion_error(client, monkeypatch, tmp_path):
  with Session() as session:
    order_id = session.query(Order.id).first()[0]

  def fail_with_specific_error(*args, **kwargs):
    raise RaeProductDeletionError('Impossibile eliminare un prodotto RAE già smaltito')

  monkeypatch.setattr(orders_module, 'update_order', fail_with_specific_error)
  monkeypatch.setattr(hooks, 'send_telegram_error', lambda _traceback: None)
  register_flask_hooks(client.application, str(tmp_path))
  response = client.put(
    f'/order/{order_id}',
    json={},
    headers=auth_header_for('admin', role=UserRole.ADMIN),
  )

  assert response.status_code == 200
  assert response.get_json() == {
    'status': 'ko',
    'message': 'Errore generico',
  }

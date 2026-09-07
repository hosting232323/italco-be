"""/schedule/suggestions?strategy=ai : gating e integrazione con il planner AI.

La CLI e' sostituita da un finto run_claude; qui si verifica il contratto
dell'endpoint (flag d'ambiente, strategia sconosciuta, forma della risposta,
errore di pianificazione riportato come ko).
"""

import json
from datetime import date

from src.database.enum import OrderStatus, UserRole

from tests.unit.factories import (
  auth_header,
  create_delivery_info,
  create_order,
  create_product,
  create_transport,
  create_user,
  customer_with_service,
)


WORK_DATE = '2026-07-15'
SUGGESTIONS = f'/schedule/suggestions?work_date={WORK_DATE}&min_size_group=1&max_size_group=5&max_distance_km=10'


def _fake_run_claude(monkeypatch, payload):
  raw = payload if isinstance(payload, str) else json.dumps(payload)
  monkeypatch.setattr('src.schedulation.ai.planner.run_claude', lambda *args, **kwargs: raw)


def _booked_order_for_date(cap='70121'):
  _, _, service_user, collection_point = customer_with_service()
  order = create_order(status=OrderStatus.BOOKED, dpc=date(2026, 7, 15), cap=cap)
  create_product(order, service_user, collection_point_id=collection_point.id)
  return order


def test_ai_strategy_disabled_by_default(client, monkeypatch):
  monkeypatch.delenv('AI_SCHEDULATION_ENABLED', raising=False)
  admin = create_user(UserRole.ADMIN)

  body = client.get(f'{SUGGESTIONS}&strategy=ai', headers=auth_header(admin)).get_json()

  assert body['status'] == 'ko'
  assert 'AI_SCHEDULATION_ENABLED' in body['message']


def test_unknown_strategy_is_rejected(client, monkeypatch):
  monkeypatch.setenv('AI_SCHEDULATION_ENABLED', '1')
  admin = create_user(UserRole.ADMIN)

  body = client.get(f'{SUGGESTIONS}&strategy=magic', headers=auth_header(admin)).get_json()

  assert body['status'] == 'ko'
  assert 'sconosciuta' in body['message']


def test_ai_strategy_returns_groups(client, monkeypatch):
  monkeypatch.setenv('AI_SCHEDULATION_ENABLED', '1')
  admin = create_user(UserRole.ADMIN)
  order = _booked_order_for_date()
  delivery = create_user(UserRole.DELIVERY)
  create_delivery_info(delivery, cap='70121')
  create_transport()

  _fake_run_claude(
    monkeypatch,
    {'groups': [{'order_ids': [order.id], 'delivery_user_id': delivery.id, 'reason': 'unico ordine'}]},
  )

  body = client.get(f'{SUGGESTIONS}&strategy=ai', headers=auth_header(admin)).get_json()

  assert body['status'] == 'ok'
  assert body['strategy'] == 'ai'
  assert len(body['groups']) == 1
  order_items = [item for item in body['groups'][0]['schedule_items'] if item['operation_type'] == 'Order']
  assert [item['order_id'] for item in order_items] == [order.id]
  assert [user['id'] for user in body['groups'][0]['delivery_users']] == [delivery.id]


def test_ai_planning_error_is_surfaced_as_ko(client, monkeypatch):
  monkeypatch.setenv('AI_SCHEDULATION_ENABLED', '1')
  admin = create_user(UserRole.ADMIN)
  _booked_order_for_date()

  _fake_run_claude(monkeypatch, 'non posso aiutarti')

  body = client.get(f'{SUGGESTIONS}&strategy=ai', headers=auth_header(admin)).get_json()

  assert body['status'] == 'ko'
  assert body['message'].startswith('Pianificazione AI non riuscita')


def test_default_strategy_still_uses_the_rule_engine(client, monkeypatch):
  monkeypatch.setenv('AI_SCHEDULATION_ENABLED', '1')
  admin = create_user(UserRole.ADMIN)
  order = _booked_order_for_date()
  delivery = create_user(UserRole.DELIVERY)
  create_delivery_info(delivery, cap='70121')
  # Se il default toccasse la CLI, questo patch la farebbe esplodere.
  monkeypatch.setattr(
    'src.schedulation.ai.planner.run_claude',
    lambda *a, **k: (_ for _ in ()).throw(AssertionError('CLI non deve essere chiamata')),
  )

  body = client.get(SUGGESTIONS, headers=auth_header(admin)).get_json()

  assert body['status'] == 'ok'
  assert body['strategy'] == 'rules'
  assert [
    item['order_id']
    for group in body['groups']
    for item in group['schedule_items']
    if item['operation_type'] == 'Order'
  ] == [order.id]

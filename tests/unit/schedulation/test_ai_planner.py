"""Pianificatore AI: parsing e validazione della proposta del modello.

La CLI e' sostituita da un finto run_claude che restituisce la stringa che
vogliamo: qui si verifica solo che il planner accetti una proposta coerente e
respinga con un messaggio chiaro ogni scostamento dai dati di input.
"""

import json

import pytest

from src.schedulation.ai import AiPlanningError, planner
from src.schedulation.ai.cli import ClaudeCliError
from src.schedulation.ai.prompt import parse_response
from src.schedulation.clustering_rules import ClusteringContext

from tests.unit.schedulation.conftest import make_order


PRO = [{'professional': True}]

# CAP baresi vicini fra loro e uno lontano, per il controllo di distanza.
NEAR_A = '70121'
NEAR_B = '70122'
FAR = '71010'  # Foggia, ~160 km da Bari


def _context(min_size=1, max_size=5, max_km=50):
  return ClusteringContext(min_size_group=min_size, max_size_group=max_size, max_distance_km=max_km)


def _fake_cli(monkeypatch, payload):
  raw = payload if isinstance(payload, str) else json.dumps(payload)
  monkeypatch.setattr(planner, 'run_claude', lambda *args, **kwargs: raw)


def _run(orders, delivery_users=None, context=None):
  return planner.ai_execute_schedulation(orders, delivery_users or [], [], context or _context())


def test_happy_path_builds_groups_and_resolves_users(monkeypatch):
  orders = [make_order(1, NEAR_A), make_order(2, NEAR_B), make_order(3, NEAR_A)]
  users = [{'id': 7, 'nickname': 'delivery_7', 'delivery_user_info': {'cap': NEAR_A}}]
  _fake_cli(
    monkeypatch,
    {
      'groups': [
        {'order_ids': [1, 3], 'delivery_user_id': 7, 'reason': 'stesso CAP'},
        {'order_ids': [2], 'delivery_user_id': None, 'reason': 'solo'},
      ]
    },
  )

  groups = _run(orders, users)

  assert [
    sorted(item['order_id'] for item in g['schedule_items'] if item['operation_type'] == 'Order') for g in groups
  ] == [[1, 3], [2]]
  assert [u['id'] for u in groups[0]['delivery_users']] == [7]
  assert groups[1]['delivery_users'] == []
  assert all(g['transports'] == [] for g in groups)


def test_rejects_unknown_order_id(monkeypatch):
  _fake_cli(monkeypatch, {'groups': [{'order_ids': [1, 999], 'delivery_user_id': None}]})
  with pytest.raises(AiPlanningError, match='inesistenti'):
    _run([make_order(1, NEAR_A)])


def test_rejects_order_left_unplanned(monkeypatch):
  _fake_cli(monkeypatch, {'groups': [{'order_ids': [1], 'delivery_user_id': None}]})
  with pytest.raises(AiPlanningError, match='non pianificati'):
    _run([make_order(1, NEAR_A), make_order(2, NEAR_B)])


def test_rejects_order_assigned_twice(monkeypatch):
  _fake_cli(
    monkeypatch,
    {'groups': [{'order_ids': [1], 'delivery_user_id': None}, {'order_ids': [1], 'delivery_user_id': None}]},
  )
  with pytest.raises(AiPlanningError, match="gia' assegnati"):
    _run([make_order(1, NEAR_A)])


def test_rejects_group_over_max_size(monkeypatch):
  orders = [make_order(i, NEAR_A) for i in range(1, 5)]
  _fake_cli(monkeypatch, {'groups': [{'order_ids': [1, 2, 3, 4], 'delivery_user_id': None}]})
  with pytest.raises(AiPlanningError, match='fuori dai limiti'):
    _run(orders, context=_context(min_size=1, max_size=3))


def test_rejects_too_many_professional_orders(monkeypatch):
  orders = [make_order(i, NEAR_A, services=PRO) for i in range(1, 4)]
  _fake_cli(monkeypatch, {'groups': [{'order_ids': [1, 2, 3], 'delivery_user_id': None}]})
  with pytest.raises(AiPlanningError, match='professionali'):
    _run(orders)


def test_rejects_group_spanning_more_than_max_distance(monkeypatch):
  orders = [make_order(1, NEAR_A), make_order(2, FAR)]
  _fake_cli(monkeypatch, {'groups': [{'order_ids': [1, 2], 'delivery_user_id': None}]})
  with pytest.raises(AiPlanningError, match='distanza interna'):
    _run(orders, context=_context(max_km=50))


def test_rejects_unknown_delivery_user(monkeypatch):
  _fake_cli(monkeypatch, {'groups': [{'order_ids': [1], 'delivery_user_id': 999}]})
  with pytest.raises(AiPlanningError, match='non tra quelli disponibili'):
    _run([make_order(1, NEAR_A)], [{'id': 7, 'delivery_user_info': {'cap': NEAR_A}}])


def test_rejects_delivery_user_used_in_two_groups(monkeypatch):
  orders = [make_order(1, NEAR_A), make_order(2, NEAR_B)]
  users = [{'id': 7, 'delivery_user_info': {'cap': NEAR_A}}]
  _fake_cli(
    monkeypatch,
    {'groups': [{'order_ids': [1], 'delivery_user_id': 7}, {'order_ids': [2], 'delivery_user_id': 7}]},
  )
  with pytest.raises(AiPlanningError, match="gia' assegnato a un altro gruppo"):
    _run(orders, users)


def test_rejects_response_without_groups(monkeypatch):
  _fake_cli(monkeypatch, {'groups': []})
  with pytest.raises(AiPlanningError, match='alcun gruppo'):
    _run([make_order(1, NEAR_A)])


def test_rejects_non_json_response(monkeypatch):
  _fake_cli(monkeypatch, 'mi spiace, non posso aiutarti')
  with pytest.raises(AiPlanningError, match='JSON valido'):
    _run([make_order(1, NEAR_A)])


def test_wraps_cli_error(monkeypatch):
  def _boom(*args, **kwargs):
    raise ClaudeCliError('CLI non trovata')

  monkeypatch.setattr(planner, 'run_claude', _boom)
  with pytest.raises(AiPlanningError, match='Chiamata al modello fallita'):
    _run([make_order(1, NEAR_A)])


def test_parse_response_strips_markdown_fences():
  assert parse_response('```json\n{"groups": []}\n```') == {'groups': []}
  assert parse_response('ecco:\n{"groups": [{"order_ids": [1]}]}\n') == {'groups': [{'order_ids': [1]}]}

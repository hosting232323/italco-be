from types import SimpleNamespace

import src.end_points.schedule.delivery as delivery


DELIVERY_USER = SimpleNamespace(id=27)


def test_get_items_for_delivery_without_schedules_returns_ok_empty(monkeypatch):
  monkeypatch.setattr(delivery, 'query_schedules', lambda filters, get_services: [])

  response = delivery.get_items_for_delivery(DELIVERY_USER)

  assert response == {'status': 'ok', 'schedule_items': []}


def test_get_items_for_delivery_with_single_schedule_returns_sorted_items(monkeypatch):
  schedule = {'schedule_items': [{'index': 2}, {'index': 1}]}
  monkeypatch.setattr(delivery, 'query_schedules', lambda filters, get_services: [('tupla',)])
  monkeypatch.setattr(delivery, 'format_query_result', lambda tupla, schedules: [schedule])

  response = delivery.get_items_for_delivery(DELIVERY_USER)

  assert response['status'] == 'ok'
  assert response['schedule_items'] == [{'index': 1}, {'index': 2}]


def test_get_items_for_delivery_with_multiple_schedules_returns_ko(monkeypatch):
  schedules = [{'schedule_items': []}, {'schedule_items': []}]
  monkeypatch.setattr(delivery, 'query_schedules', lambda filters, get_services: [('tupla',)])
  monkeypatch.setattr(delivery, 'format_query_result', lambda tupla, _: schedules)

  response = delivery.get_items_for_delivery(DELIVERY_USER)

  assert response == {'status': 'ko', 'message': 'Numero di bordero trovati non valido'}

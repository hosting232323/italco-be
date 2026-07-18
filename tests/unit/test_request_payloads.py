from types import SimpleNamespace

from flask import Flask, request

from src.database.enum import OrderType
from src.end_points import collection_point as collection_point_module
from src.end_points import orders as orders_module
from src.end_points import service as service_module
from src.end_points.orders import update_order_endpoint
from src.end_points.rae import disposal as disposal_module


class StubEntity:
  def __init__(self, id=1, version=1):
    self.id = id
    self.version = version

  def to_dict(self):
    return {'id': self.id}


class StubSession:
  def __enter__(self):
    return self

  def __exit__(self, *_args):
    return None

  def commit(self):
    return None


def test_order_update_keeps_request_payload_unchanged(monkeypatch):
  app = Flask(__name__)
  order = StubEntity()
  monkeypatch.setattr(orders_module, 'SessionWithStorage', StubSession)
  monkeypatch.setattr(orders_module, 'get_by_id', lambda *_args, **_kwargs: order)

  def mutate_update_data(_user, _order, data, _session, pending_sms=None):
    data['status'] = object()
    data.pop('external_status')
    data['products']['tv']['services'].append({'id': 99})
    data['products']['tv']['release_collection_point_id'] = 0
    return None

  monkeypatch.setattr(orders_module, 'update_order', mutate_update_data)
  monkeypatch.setattr(orders_module, 'save_order_status_to_euronics', lambda _order: None)
  monkeypatch.setattr(orders_module, 'mailer_check', lambda *_args: None)

  payload = {
    'version': 1,
    'status': 'Booked',
    'external_status': 'CONFIRMED',
    'products': {'tv': {'services': [{'id': 1}]}},
  }
  with app.test_request_context('/order/1', method='PUT', json=payload):
    update_order_endpoint.__wrapped__(SimpleNamespace(), 1)
    assert request.get_json() == {
      'version': 1,
      'status': 'Booked',
      'external_status': 'CONFIRMED',
      'products': {'tv': {'services': [{'id': 1}]}},
    }


def test_rae_disposal_keeps_input_payload_unchanged(monkeypatch):
  payload = {'carrier_id': 3, 'rae_product_ids': [10, 11]}
  captured = {}

  def create(_model, data, session=None):
    captured['data'] = data
    return StubEntity()

  monkeypatch.setattr(disposal_module, 'Session', StubSession)
  monkeypatch.setattr(disposal_module, 'create', create)
  monkeypatch.setattr(disposal_module, 'get_by_ids', lambda *_args, **_kwargs: [])

  disposal_module.create_rae_disposal(payload)

  assert payload == {'carrier_id': 3, 'rae_product_ids': [10, 11]}
  assert captured['data'] == {'carrier_id': 3}


def test_collection_point_create_keeps_request_payload_unchanged(monkeypatch):
  app = Flask(__name__)
  captured = {}

  def create(_model, data):
    captured.update(data)
    return StubEntity()

  monkeypatch.setattr(collection_point_module, 'create', create)
  payload = {'name': 'Depot'}
  with app.test_request_context('/collection-point', method='POST', json=payload):
    collection_point_module.create_collection_point.__wrapped__(SimpleNamespace(id=7))
    assert request.get_json() == payload
  assert captured == {'name': 'Depot', 'user_id': 7}


def test_service_create_keeps_request_payload_unchanged(monkeypatch):
  app = Flask(__name__)
  captured = {}

  def create(_model, data):
    captured.update(data)
    return StubEntity()

  monkeypatch.setattr(service_module, 'create', create)
  payload = {'name': 'Delivery', 'type': OrderType.DELIVERY.value}
  with app.test_request_context('/service', method='POST', json=payload):
    service_module.create_service.__wrapped__(None)
    assert request.get_json() == payload
  assert captured['type'] == OrderType.DELIVERY


def test_service_update_keeps_request_payload_unchanged(monkeypatch):
  app = Flask(__name__)
  captured = {}
  monkeypatch.setattr(service_module, 'get_by_id', lambda *_args: StubEntity())

  def update(_entity, data):
    captured.update(data)
    return StubEntity()

  monkeypatch.setattr(service_module, 'update', update)
  payload = {'name': 'Pickup', 'type': OrderType.WITHDRAW.value}
  with app.test_request_context('/service/1', method='PUT', json=payload):
    service_module.update_service.__wrapped__(None, 1)
    assert request.get_json() == payload
  assert captured['type'] == OrderType.WITHDRAW

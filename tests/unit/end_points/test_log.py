import src.end_points.log as log_endpoints
from src.database.enum import UserRole

from tests.unit.factories import auth_header, create_user


def test_get_logs_formats_entries(client, monkeypatch):
  admin = create_user(UserRole.ADMIN)
  entries = [{'id': 'log-1', 'user_id': 7, 'identifier': 'admin', 'path': '/order'}]
  captured = {}

  def fake_query_logs(filters, folder):
    captured['filters'] = filters
    return entries

  monkeypatch.setattr(log_endpoints, 'query_logs', fake_query_logs)

  response = client.post('/log/filter', json={'filters': {'user': 'admin'}}, headers=auth_header(admin))

  body = response.get_json()
  assert body['status'] == 'ok'
  assert captured['filters'] == {'user': 'admin'}
  assert body['logs'][0]['user'] == {'id': 7, 'identifier': 'admin'}
  assert body['logs'][0]['logs']['path'] == '/order'


def test_get_log_found(client, monkeypatch):
  admin = create_user(UserRole.ADMIN)
  monkeypatch.setattr(log_endpoints, 'find_log', lambda log_id, folder: {'id': log_id})
  monkeypatch.setattr(log_endpoints, 'format_log', lambda entry: {'formatted': entry['id']})

  response = client.get('/log/abc123', headers=auth_header(admin))

  body = response.get_json()
  assert body['status'] == 'ok'
  assert body['log'] == {'formatted': 'abc123'}


def test_get_log_not_found(client, monkeypatch):
  admin = create_user(UserRole.ADMIN)
  monkeypatch.setattr(log_endpoints, 'find_log', lambda log_id, folder: None)

  response = client.get('/log/missing', headers=auth_header(admin))

  body = response.get_json()
  assert body['status'] == 'ko'
  assert body['message'] == 'Log non trovato'


def test_log_endpoints_require_admin(client):
  operator = create_user(UserRole.OPERATOR)

  response = client.post('/log/filter', json={'filters': {}}, headers=auth_header(operator))

  assert response.get_json()['status'] == 'ko'

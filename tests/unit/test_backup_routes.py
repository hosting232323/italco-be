"""Test delle route di backup e manutenzione definite in src/__init__.py."""

import api
import src


def test_backup_routes_denied_without_swagger_key(client, monkeypatch):
  monkeypatch.setattr(api, 'SWAGGER_KEY', None)

  assert client.get('/internal-backup').get_json()['status'] == 'ko'
  assert client.get('/folder-backup').get_json()['status'] == 'ko'


def test_internal_backup_runs_when_authorized(client, monkeypatch):
  monkeypatch.setattr(api, 'SWAGGER_KEY', 'secret')
  calls = []
  monkeypatch.setattr(src, 'db_backup', lambda url, server=False: calls.append((url, server)))

  response = client.get('/internal-backup', headers={'SwaggerAuthorization': 'secret'})

  body = response.get_json()
  assert body['status'] == 'ok'
  assert body['message'] == 'Operazione completata con successo!'
  assert len(calls) == 1
  assert calls[0][1] is True  # server=True


def test_folder_backup_runs_when_authorized(client, monkeypatch):
  monkeypatch.setattr(api, 'SWAGGER_KEY', 'secret')
  calls = []
  monkeypatch.setattr(src, 'folder_backup', lambda folder, server=False: calls.append((folder, server)))

  response = client.get('/folder-backup', headers={'SwaggerAuthorization': 'secret'})

  body = response.get_json()
  assert body['status'] == 'ok'
  assert len(calls) == 1
  assert calls[0][1] is True

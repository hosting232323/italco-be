"""Cosa finisce nel log delle richieste (analisi privacy del 15/10).

Il log tiene tutte le richieste con i loro body, ma per login, gestione utenti,
tracking pubblico e richiesta demo basta sapere chi ha chiamato cosa e com'e'
andata: i body portano credenziali, posizioni dei corrieri e dati di persone
che non sono utenti della piattaforma.
"""

import inspect
import json
from pathlib import Path

import pytest
from api import register_flask_hooks
from flask import Flask

import src as app_module


SUPPORTS_BODY_EXCLUSION = 'body_excluded_prefixes' in inspect.signature(register_flask_hooks).parameters


def _log_entries():
  files = Path(app_module.STATIC_FOLDER).glob('*/logs/*/*.jsonl')
  return [json.loads(line) for file in files for line in file.read_text(encoding='utf-8').splitlines()]


def test_log_hooks_exclude_the_bodies_of_sensitive_paths(monkeypatch):
  calls = []

  def fake_register(
    app, log_folder, excluded_paths=(), excluded_prefixes=(), user_log_field=None, body_excluded_prefixes=()
  ):
    calls.append({'user_log_field': user_log_field, 'body_excluded_prefixes': body_excluded_prefixes})

  monkeypatch.setattr(app_module, 'register_flask_hooks', fake_register)

  app_module._register_log_hooks(Flask(__name__))

  assert calls == [{'user_log_field': 'nickname', 'body_excluded_prefixes': app_module.LOG_BODY_EXCLUDED_PREFIXES}]
  assert {'/user', '/order/public', '/demo-request'} <= set(app_module.LOG_BODY_EXCLUDED_PREFIXES)


def test_log_hooks_still_start_with_an_older_generic_lib(monkeypatch):
  calls = []

  def old_register(app, log_folder, excluded_paths=(), excluded_prefixes=(), user_log_field=None):
    calls.append(user_log_field)

  monkeypatch.setattr(app_module, 'register_flask_hooks', old_register)

  app_module._register_log_hooks(Flask(__name__))

  assert calls == ['nickname']


@pytest.mark.skipif(not SUPPORTS_BODY_EXCLUSION, reason='generic-lib senza body_excluded_prefixes')
def test_login_body_and_response_do_not_reach_the_log(client):
  client.post('/user/login', json={'email': 'nessuno', 'password': 'password-in-chiaro'})

  entries = [entry for entry in _log_entries() if entry['request'].get('path') == '/user/login']
  assert entries
  assert 'password-in-chiaro' not in json.dumps(entries)
  assert entries[-1]['request'] == {'method': 'POST', 'path': '/user/login'}
  assert entries[-1]['response'] == {'status': 'ko'}

"""Test di `python -m src.checks`, i check lanciati dal container italco-be-jobs."""

import logging
import runpy
import threading
import time
import warnings

import api.storage
import api.telegram
import database_api
import pytest

import src
from src import checks


class EmptySession:
  # Ogni query della sessione finta torna vuota, qualunque catena di filtri e join.
  def __enter__(self):
    return self

  def __exit__(self, *_):
    return None

  def all(self):
    return []

  def __getattr__(self, name):
    return lambda *args, **kwargs: self


def test_removed_routes_return_404():
  # Backup e check li fa il container dei lavori: gli endpoint chiamati da
  # cron-job.org non esistono piu'.
  client = src.app.test_client()

  for path in ('/internal-backup', '/folder-backup', '/checks'):
    assert client.get(path).status_code == 404


def test_run_checks_runs_the_checks_on_the_static_folder(monkeypatch):
  folders = []
  monkeypatch.setattr(checks, 'trigger_checks', folders.append)

  checks.run_checks()

  assert folders == [src.STATIC_FOLDER]


def test_run_checks_waits_for_the_telegram_threads(monkeypatch):
  sent = []

  def slow_send():
    time.sleep(0.2)
    sent.append('report')

  monkeypatch.setattr(checks, 'trigger_checks', lambda folder: threading.Thread(target=slow_send, daemon=True).start())

  checks.run_checks()

  assert sent == ['report']


def test_run_checks_logs_one_line(monkeypatch, caplog):
  monkeypatch.setattr(checks, 'trigger_checks', lambda folder: None)

  with caplog.at_level(logging.INFO, logger=checks.__name__):
    checks.run_checks()

  records = [record for record in caplog.records if record.name == checks.__name__]
  assert len(records) == 1
  assert 'terminati' in records[0].getMessage()


def test_run_checks_reports_an_error_on_telegram_and_fails(monkeypatch):
  errors = []

  def broken(folder):
    raise RuntimeError('database giu')

  monkeypatch.setattr(checks, 'trigger_checks', broken)
  monkeypatch.setattr(checks, 'send_telegram_error', lambda trace, endpoint=True: errors.append((trace, endpoint)))

  with pytest.raises(RuntimeError):
    checks.run_checks()

  assert len(errors) == 1
  assert 'database giu' in errors[0][0]
  assert errors[0][1] is False


def test_module_main_sets_the_database_and_runs_the_checks(monkeypatch):
  databases = []
  mismatches = []
  messages = []
  monkeypatch.setattr(logging, 'basicConfig', lambda **kwargs: None)
  monkeypatch.setattr(database_api, 'set_database', databases.append)
  monkeypatch.setattr(database_api, 'Session', EmptySession)
  monkeypatch.setattr(api.storage, 'check_mismatch', lambda *args: mismatches.append(args))
  monkeypatch.setattr(api.telegram, 'send_telegram_message', messages.append)

  # Il modulo e' gia' importato dai test: runpy avvisa che lo riesegue da capo.
  with warnings.catch_warnings():
    warnings.simplefilter('ignore', RuntimeWarning)
    runpy.run_module('src.checks', run_name='__main__')

  assert databases == [src.DATABASE_URL]
  assert len(messages) == 1
  assert 'Report Dati Corrotti' in messages[0]
  assert [args[1] for args in mismatches] == [src.STATIC_FOLDER] * 4

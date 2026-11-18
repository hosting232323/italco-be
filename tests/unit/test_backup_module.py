"""Test di src/backup.py, il backup lanciato dal container italco-be-jobs."""

import logging
import os
import subprocess
import threading
import time

import database_api.backup
import pytest

import src
from src import backup


def test_run_backup_calls_db_and_folder_backup_in_server_mode(monkeypatch):
  calls = []
  monkeypatch.setattr(backup, 'db_backup', lambda url, server=False: calls.append(('db', url, server)))
  monkeypatch.setattr(backup, 'folder_backup', lambda folder, server=False: calls.append(('folder', folder, server)))

  backup.run_backup()

  assert calls == [
    ('db', src.DATABASE_URL, True),
    ('folder', os.path.join(src.STATIC_FOLDER, 'prod'), True),
  ]


def test_run_backup_waits_for_the_backup_threads(monkeypatch):
  finished = []

  def slow(name):
    time.sleep(0.2)
    finished.append(name)

  def fake_db_backup(url, server=False):
    threading.Thread(target=slow, args=('db',), daemon=True).start()

  def fake_folder_backup(folder, server=False):
    # Come la notifica Telegram: un thread che ne avvia un altro.
    def run():
      threading.Thread(target=slow, args=('telegram',), daemon=True).start()

    threading.Thread(target=run, daemon=True).start()

  monkeypatch.setattr(backup, 'db_backup', fake_db_backup)
  monkeypatch.setattr(backup, 'folder_backup', fake_folder_backup)

  backup.run_backup()

  assert sorted(finished) == ['db', 'telegram']


def test_run_backup_logs_one_line(monkeypatch, caplog):
  monkeypatch.setattr(backup, 'db_backup', lambda url, server=False: None)
  monkeypatch.setattr(backup, 'folder_backup', lambda folder, server=False: None)

  with caplog.at_level(logging.INFO, logger=backup.__name__):
    backup.run_backup()

  records = [record for record in caplog.records if record.name == backup.__name__]
  assert len(records) == 1
  assert 'terminati' in records[0].getMessage()


def test_wait_for_threads_ignores_threads_started_before():
  release = threading.Event()
  older = threading.Thread(target=release.wait, daemon=True)
  older.start()
  try:
    backup.wait_for_threads(set(threading.enumerate()))
    assert older.is_alive()
  finally:
    release.set()
    older.join()


def test_check_dump_reads_the_whole_file(monkeypatch):
  calls = []
  monkeypatch.setattr(backup.subprocess, 'run', lambda args, **kwargs: calls.append((args, kwargs)))

  backup.check_dump('260101000000.dump')

  assert calls[0][0] == ['pg_restore', f'--file={os.devnull}', '260101000000.dump']
  assert calls[0][1]['check'] is True


def test_check_dump_raises_on_a_truncated_dump(monkeypatch):
  def fail(args, **kwargs):
    raise subprocess.CalledProcessError(1, args, stderr='could not read from input file')

  monkeypatch.setattr(backup.subprocess, 'run', fail)

  with pytest.raises(subprocess.CalledProcessError):
    backup.check_dump('260101000000.dump')


def test_run_backup_checks_the_dump_before_uploading_it(monkeypatch):
  steps = []
  original = database_api.backup.upload_backup
  monkeypatch.setattr(backup, 'check_dump', lambda path: steps.append(('check', path)))
  monkeypatch.setattr(backup, 'upload_backup', lambda path, server=None: steps.append(('upload', path, server)))
  # Come db_backup: carica il dump con la upload_backup del modulo della lib.
  monkeypatch.setattr(
    backup, 'db_backup', lambda url, server=False: database_api.backup.upload_backup('260101000000.dump', server)
  )
  monkeypatch.setattr(backup, 'folder_backup', lambda folder, server=False: None)

  backup.run_backup()

  assert steps == [('check', '260101000000.dump'), ('upload', '260101000000.dump', True)]
  assert database_api.backup.upload_backup is original


def test_run_backup_does_not_upload_an_unreadable_dump(monkeypatch):
  uploaded = []

  def broken(path):
    raise subprocess.CalledProcessError(1, ['pg_restore'])

  def fake_db_backup(url, server=False):
    with pytest.raises(subprocess.CalledProcessError):
      database_api.backup.upload_backup('260101000000.dump', server)

  monkeypatch.setattr(backup, 'check_dump', broken)
  monkeypatch.setattr(backup, 'upload_backup', lambda path, server=None: uploaded.append(path))
  monkeypatch.setattr(backup, 'db_backup', fake_db_backup)
  monkeypatch.setattr(backup, 'folder_backup', lambda folder, server=False: None)

  backup.run_backup()

  assert uploaded == []

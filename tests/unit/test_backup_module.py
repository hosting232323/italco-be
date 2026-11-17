"""Test di src/backup.py, il backup lanciato dal container italco-be-backup."""

import logging
import os
import threading
import time

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

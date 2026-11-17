"""Backup di produzione: dump del database e cartella prod, verso la macchina di backup.

Sono le stesse chiamate di /internal-backup e /folder-backup (src/__init__.py),
ma lanciate da dentro: il container italco-be-backup (gitlab/deploy.yml, solo
in produzione) esegue `python -m src.backup` agli orari di BACKUP_TIMES con
backup.sh, invece di aspettare la chiamata di cron-job.org all'API.

db_backup e folder_backup di generic-lib partono in un thread daemon e
tornano subito; un errore lo segnalano loro su Telegram. Qui il processo
aspetta quei thread, cosi' il backup e' finito quando il comando e' finito
(e il lock di backup.sh resta preso per tutta la durata).

L'import di src carica solo l'app Flask di base, senza blueprint e senza
connessione al database (set_database e' in src/__main__.py): DATABASE_URL e
STATIC_FOLDER sono letti li', come per gli endpoint.
"""

import logging
import os
import threading
import time

from api.storage import folder_backup
from database_api.backup import db_backup
from . import DATABASE_URL, STATIC_FOLDER


logger = logging.getLogger(__name__)


def wait_for_threads(before):
  # I thread nati dopo `before` possono avviarne altri (la notifica Telegram
  # di un errore parte in un thread suo): si ricontrolla finche' non ne resta
  # nessuno, altrimenti l'uscita del processo li interromperebbe.
  while True:
    started = [
      thread for thread in threading.enumerate() if thread not in before and thread is not threading.current_thread()
    ]
    if not started:
      return
    for thread in started:
      thread.join()


def run_backup():
  started_at = time.monotonic()
  before = set(threading.enumerate())
  folder = os.path.join(STATIC_FOLDER, 'prod')
  db_backup(DATABASE_URL, server=True)
  folder_backup(folder, server=True)
  wait_for_threads(before)
  # Un errore lo segnala generic-lib su Telegram: qui solo la riga che dice
  # che il giro c'e' stato e quanto e' durato.
  logger.info('backup: database e %s terminati in %ds', folder, round(time.monotonic() - started_at))


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
  run_backup()

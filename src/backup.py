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
import subprocess
import threading
import time

import database_api.backup
from api.storage import folder_backup
from database_api.backup import db_backup, upload_backup
from . import DATABASE_URL, STATIC_FOLDER


logger = logging.getLogger(__name__)


def check_dump(path):
  # Come in Stepbound: prima di inviarlo, il dump deve potersi leggere tutto.
  # `pg_restore --list` non basta, legge solo l'indice che pg_dump scrive in
  # testa al file, e un dump troncato dopo l'indice passerebbe. Ricostruirlo
  # come script verso /dev/null legge i dati di ogni tabella: un file tagliato
  # finisce con "could not read from input file". Dimostra che il file e'
  # intero, non che si ripristina su un database (quello e' una prova di restore).
  subprocess.run(
    ['pg_restore', f'--file={os.devnull}', path],
    check=True,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.PIPE,
    text=True,
  )


def upload_checked_backup(file_path, server=None):
  # Prende il posto di upload_backup dentro db_backup per la durata del giro:
  # un dump illeggibile solleva qui, e db_backup lo tratta come ogni altro
  # errore (avviso Telegram, dump tenuto nella cartella di ripiego).
  check_dump(file_path)
  return upload_backup(file_path, server)


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
  # Si rimette la funzione che c'era, qualunque fosse, a fine giro.
  original_upload = database_api.backup.upload_backup
  database_api.backup.upload_backup = upload_checked_backup
  try:
    db_backup(DATABASE_URL, server=True)
    folder_backup(folder, server=True)
    wait_for_threads(before)
  finally:
    database_api.backup.upload_backup = original_upload
  # Un errore lo segnala generic-lib su Telegram: qui solo la riga che dice
  # che il giro c'e' stato e quanto e' durato.
  logger.info('backup: database e %s terminati in %ds', folder, round(time.monotonic() - started_at))


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
  run_backup()

"""Cancella i dati personali scaduti (privacy: periodi di conservazione).

Da lanciare ogni giorno da cron sul server (vedi docs/data-retention.md). Le
durate si configurano con variabili d'ambiente; vuota o non numerica = valore
di default, 0 o negativo = quella pulizia è disattivata.

  RETENTION_POSITION_HOURS=24         ultima posizione del corriere (ore)
  RETENTION_POSITION_EVENTS_DAYS=365  eventi di attivazione/chiusura della posizione (giorni)
  RETENTION_DEMO_REQUEST_DAYS=365     richieste demo salvate in archivio (giorni)
  RETENTION_LOG_DAYS=90               log di audit delle richieste (giorni)

  python -m scripts.retention_cleanup             # cancella
  python -m scripts.retention_cleanup --dry-run   # conta e basta
"""

# ruff: noqa: T201
import argparse
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from api.settings import IS_DEV
from sqlalchemy import create_engine, text

from src import STATIC_FOLDER

DEFAULTS = {
  'RETENTION_POSITION_HOURS': 24,
  'RETENTION_POSITION_EVENTS_DAYS': 365,
  'RETENTION_DEMO_REQUEST_DAYS': 365,
  'RETENTION_LOG_DAYS': 90,
}


def retention_setting(name: str) -> int:
  """Durata configurata; senza valore valido vale il default. 0 o meno disattiva."""
  try:
    return int(os.environ.get(name, '').strip())
  except ValueError:
    return DEFAULTS[name]


def _count_or_run(connection, count_sql: str, run_sql: str, params: dict, dry_run: bool) -> int:
  count = connection.execute(text(count_sql), params).scalar()
  if count and not dry_run:
    connection.execute(text(run_sql), params)
  return count


def clear_old_positions(connection, hours: int, dry_run: bool) -> int:
  """Azzera l'ultima posizione dei corrieri non aggiornata da `hours` ore."""
  where = '(lat IS NOT NULL OR lon IS NOT NULL) AND updated_at < :cutoff'
  return _count_or_run(
    connection,
    f'SELECT count(*) FROM delivery_user_info WHERE {where}',
    f'UPDATE delivery_user_info SET lat = NULL, lon = NULL WHERE {where}',
    {'cutoff': datetime.now(timezone.utc) - timedelta(hours=hours)},
    dry_run,
  )


def delete_old_position_events(connection, days: int, dry_run: bool) -> int:
  """Cancella gli eventi di posizione vecchi di `days` giorni.

  L'ultimo evento di un borderò ancora aperto (non di chiusura) resta sempre:
  è quello che dice chi tiene la posizione. Se l'ultimo è una chiusura,
  cancellare tutta la storia dà lo stesso risultato di "nessun tenitore".
  """
  where = """created_at < :cutoff AND NOT (
    type::text <> 'CLOSING'
    AND id = (SELECT max(e.id) FROM schedule_item_user e WHERE e.schedule_id = s.schedule_id)
  )"""
  return _count_or_run(
    connection,
    f'SELECT count(*) FROM schedule_item_user s WHERE {where}',
    f'DELETE FROM schedule_item_user s WHERE {where}',
    {'cutoff': datetime.now(timezone.utc) - timedelta(days=days)},
    dry_run,
  )


def delete_old_demo_requests(connection, days: int, dry_run: bool) -> int:
  """Cancella le richieste demo salvate in archivio (tabella mail) più vecchie di `days` giorni."""
  where = 'created_at < :cutoff'
  return _count_or_run(
    connection,
    f'SELECT count(*) FROM mail WHERE {where}',
    f'DELETE FROM mail WHERE {where}',
    {'cutoff': datetime.now(timezone.utc) - timedelta(days=days)},
    dry_run,
  )


def delete_old_logs(log_dir: Path, days: int, dry_run: bool) -> int:
  """Cancella i file di log giornalieri (AAAA-MM/AAAA-MM-GG.jsonl e indice) più vecchi di `days` giorni."""
  if not log_dir.is_dir():
    return 0

  oldest_kept = date.today() - timedelta(days=days)
  deleted = 0
  for log_file in sorted(log_dir.glob('*/*.jsonl')):
    try:
      day = date.fromisoformat(log_file.stem)
    except ValueError:
      continue
    if day >= oldest_kept:
      continue
    deleted += 1
    if dry_run:
      continue
    log_file.unlink()
    log_file.with_suffix('.idx').unlink(missing_ok=True)

  if not dry_run:
    for month_dir in log_dir.iterdir():
      if month_dir.is_dir() and not any(month_dir.iterdir()):
        month_dir.rmdir()
  return deleted


def main(argv=None) -> dict:
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument('--dry-run', action='store_true', help='conta quello che cancellerebbe, non cancella')
  args = parser.parse_args(argv)

  verb = 'da cancellare' if args.dry_run else 'cancellati'
  settings = {name: retention_setting(name) for name in DEFAULTS}
  results = {}

  with create_engine(os.environ['DATABASE_URL']).begin() as connection:
    database_jobs = [
      ('positions', 'RETENTION_POSITION_HOURS', 'ore', 'posizioni dei corrieri', clear_old_positions),
      (
        'position_events',
        'RETENTION_POSITION_EVENTS_DAYS',
        'giorni',
        'eventi di posizione',
        delete_old_position_events,
      ),
      ('demo_requests', 'RETENTION_DEMO_REQUEST_DAYS', 'giorni', 'richieste demo', delete_old_demo_requests),
    ]
    for key, variable, unit, label, job in database_jobs:
      if settings[variable] <= 0:
        print(f'{label}: disattivato ({variable})')
        continue
      results[key] = job(connection, settings[variable], args.dry_run)
      print(f'{label} {verb}: {results[key]} (oltre {settings[variable]} {unit})')

  if settings['RETENTION_LOG_DAYS'] <= 0:
    print('log di audit: disattivato (RETENTION_LOG_DAYS)')
  else:
    log_dir = Path(STATIC_FOLDER) / ('test' if IS_DEV else 'prod') / 'logs'
    results['logs'] = delete_old_logs(log_dir, settings['RETENTION_LOG_DAYS'], args.dry_run)
    print(f'file di log {verb}: {results["logs"]} (oltre {settings["RETENTION_LOG_DAYS"]} giorni)')

  return results


if __name__ == '__main__':
  main()

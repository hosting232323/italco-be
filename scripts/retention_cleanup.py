"""Cancella i dati personali scaduti (privacy: periodi di conservazione).

Da lanciare ogni giorno da cron sul server (vedi docs/data-retention.md). Le
durate si configurano con variabili d'ambiente; vuota o non numerica = valore
di default, 0 o negativo = quella pulizia è disattivata.

  RETENTION_POSITION_HOURS=24         ultima posizione del corriere (ore)
  RETENTION_POSITION_EVENTS_DAYS=365  eventi di attivazione/chiusura della posizione (giorni)
  RETENTION_DEMO_REQUEST_DAYS=365     richieste demo salvate in archivio (giorni)
  RETENTION_LOG_DAYS=90               log di audit delle richieste (giorni)
  RETENTION_DELIVERY_PROOF_MONTHS=24  foto e firma di consegna (mesi)

  python -m scripts.retention_cleanup             # cancella
  python -m scripts.retention_cleanup --dry-run   # conta e basta
"""

# ruff: noqa: T201
import argparse
import calendar
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import database_api
from api.settings import IS_DEV
from api.storage.session import SessionWithStorage
from database_api import Session, set_database
from sqlalchemy import create_engine, func, select, text

from src import STATIC_FOLDER
from src.database.enum import OrderStatus
from src.database.schema import Order, Photo

DEFAULTS = {
  'RETENTION_POSITION_HOURS': 24,
  'RETENTION_POSITION_EVENTS_DAYS': 365,
  'RETENTION_DEMO_REQUEST_DAYS': 365,
  'RETENTION_LOG_DAYS': 90,
  'RETENTION_DELIVERY_PROOF_MONTHS': 24,
}

# Foto e firma si cancellano solo per ordini chiusi: un ordine ancora in lavorazione non perde la prova.
CLOSED_ORDER_STATUSES = (OrderStatus.DELIVERED, OrderStatus.NOT_DELIVERED)
PHOTO_BATCH_SIZE = 500


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


def months_ago(today: date, months: int) -> date:
  """La data di `months` mesi fa (a fine mese si ferma all'ultimo giorno del mese di arrivo)."""
  year, month = divmod(today.year * 12 + today.month - 1 - months, 12)
  month += 1
  return date(year, month, min(today.day, calendar.monthrange(year, month)[1]))


def clear_old_signatures(connection, months: int, dry_run: bool) -> int:
  """Azzera la firma (Order.signature) degli ordini consegnati o non consegnati da più di `months` mesi.

  La data è `completion_date` dell'ordine; se manca si usa l'ultima modifica (updated_at),
  che è sempre successiva alla chiusura: nel dubbio la firma resta di più, non di meno.
  L'ordine non si cancella: i PDF e le esportazioni mostrano semplicemente la firma vuota.
  """
  where = """signature IS NOT NULL
    AND status::text IN ('DELIVERED', 'NOT_DELIVERED')
    AND COALESCE(completion_date, updated_at::date) < :cutoff"""
  return _count_or_run(
    connection,
    f'SELECT count(*) FROM "order" WHERE {where}',
    f'UPDATE "order" SET signature = NULL WHERE {where}',
    {'cutoff': months_ago(date.today(), months)},
    dry_run,
  )


def _expired_photos(cutoff: date):
  """Foto di ordini consegnati o non consegnati prima di `cutoff`.

  La data è `completion_date` dell'ordine; se manca, la data in cui la foto è stata caricata
  (la foto nasce alla chiusura della consegna). Foto di ordini ancora aperti non rientrano mai.
  """
  return (
    select(Photo)
    .join(Order, Order.id == Photo.order_id)
    .where(
      Order.status.in_(CLOSED_ORDER_STATUSES),
      func.coalesce(Order.completion_date, func.date(Photo.created_at)) < cutoff,
    )
  )


def delete_old_delivery_photos(months: int, dry_run: bool, today: date = None) -> int:
  """Cancella le foto di consegna più vecchie di `months` mesi: file e riga del database.

  Passa da SessionWithStorage, come delete_order: il file sparisce solo dopo il commit del
  database e un file già mancante non è un errore. Si lavora a lotti per non tenere una
  transazione enorme. I backup (20 giorni) possono contenere ancora la copia.
  """
  expired = _expired_photos(months_ago(today or date.today(), months))
  with Session() as session:
    count = session.execute(select(func.count()).select_from(expired.subquery())).scalar()
  if dry_run or not count:
    return count

  deleted = 0
  while True:
    with SessionWithStorage() as session:
      photos = session.execute(expired.order_by(Photo.id).limit(PHOTO_BATCH_SIZE)).scalars().all()
      if not photos:
        return deleted
      for photo in photos:
        session.delete_file(photo.link.rsplit('/', 1)[-1], STATIC_FOLDER, subfolder='photos')
        session.delete(photo)
      session.commit()
      deleted += len(photos)


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
      (
        'signatures',
        'RETENTION_DELIVERY_PROOF_MONTHS',
        'mesi',
        'firme di consegna',
        clear_old_signatures,
      ),
    ]
    for key, variable, unit, label, job in database_jobs:
      if settings[variable] <= 0:
        print(f'{label}: disattivato ({variable})')
        continue
      results[key] = job(connection, settings[variable], args.dry_run)
      print(f'{label} {verb}: {results[key]} (oltre {settings[variable]} {unit})')

  months = settings['RETENTION_DELIVERY_PROOF_MONTHS']
  if months <= 0:
    print('foto di consegna: disattivato (RETENTION_DELIVERY_PROOF_MONTHS)')
  else:
    if database_api.engine is None:
      set_database(os.environ['DATABASE_URL'])
    results['photos'] = delete_old_delivery_photos(months, args.dry_run)
    print(f'foto di consegna {verb}: {results["photos"]} (oltre {months} mesi)')

  if settings['RETENTION_LOG_DAYS'] <= 0:
    print('log di audit: disattivato (RETENTION_LOG_DAYS)')
  else:
    log_dir = Path(STATIC_FOLDER) / ('test' if IS_DEV else 'prod') / 'logs'
    results['logs'] = delete_old_logs(log_dir, settings['RETENTION_LOG_DAYS'], args.dry_run)
    print(f'file di log {verb}: {results["logs"]} (oltre {settings["RETENTION_LOG_DAYS"]} giorni)')

  return results


if __name__ == '__main__':
  main()

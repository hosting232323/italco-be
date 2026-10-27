import time
from flask import request
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from database_api import Session, scope as db_scope

from .database.schema import RateLimitCounter

WINDOW_SECONDS = 3600

# Contatore su PostgreSQL: il limite resta coerente tra worker e istanze.


def client_ip() -> str:
  # Cloudflare imposta questo header all'ingresso. X-Forwarded-For puo' invece
  # contenere valori forniti dal client e non va usato come identita' attendibile.
  return request.headers.get('CF-Connecting-IP', '').strip() or request.remote_addr or 'unknown'


def rate_limited(ip: str, scope: str, max_attempts: int) -> bool:
  now = int(time.time())
  bucket_start = now // WINDOW_SECONDS * WINDOW_SECONDS
  table = RateLimitCounter.__table__
  statement = insert(table).values(scope=scope, ip=ip, bucket_start=bucket_start, attempts=1)
  statement = statement.on_conflict_do_update(
    index_elements=['scope', 'ip', 'bucket_start'],
    set_={'attempts': table.c.attempts + 1},
  ).returning(table.c.attempts)
  with db_scope(company_id=None), Session() as session:
    attempts = session.execute(statement).scalar_one()
    if now % WINDOW_SECONDS < 10:
      session.execute(delete(table).where(table.c.bucket_start < bucket_start - WINDOW_SECONDS))
    session.commit()
  return attempts > max_attempts

import threading
import time
from flask import request

WINDOW_SECONDS = 3600

# Chiave (scope, ip): ogni endpoint ha il suo budget. In memoria e per processo:
# con piu' worker gunicorn il limite effettivo e' moltiplicato, e X-Forwarded-For
# e' falsificabile. Un freno agli abusi, non una barriera.
_attempts: dict[tuple[str, str], list[float]] = {}
_attempts_lock = threading.Lock()


def client_ip() -> str:
  # Dietro il proxy remote_addr e' quello del proxy: conta il primo hop di
  # X-Forwarded-For.
  forwarded = request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
  return forwarded or request.remote_addr or 'unknown'


def rate_limited(ip: str, scope: str, max_attempts: int) -> bool:
  now = time.time()
  with _attempts_lock:
    recent = [stamp for stamp in _attempts.get((scope, ip), []) if now - stamp < WINDOW_SECONDS]
    if len(recent) >= max_attempts:
      _attempts[(scope, ip)] = recent
      return True
    recent.append(now)
    _attempts[(scope, ip)] = recent
    # Sfoltisce le voci scadute degli altri indirizzi, cosi' il dizionario non cresce all'infinito.
    for other in [key for key, stamps in _attempts.items() if not any(now - s < WINDOW_SECONDS for s in stamps)]:
      del _attempts[other]
    return False

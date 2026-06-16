import io
import json
import os
import decimal
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytz
from tqdm import tqdm


ROME_TZ = pytz.timezone('Europe/Rome')


def _serialize_default(o):
  return float(o) if isinstance(o, decimal.Decimal) else str(o)


# ---------------------------------------------------------------------------
# Lettura dal dump
# ---------------------------------------------------------------------------

def _pg_restore_table(dump_path: str, table: str) -> list[list[str]]:
  """Estrae le righe COPY di una tabella dal dump come lista di colonne (tab-separated)."""
  result = subprocess.run(
    ['pg_restore', '-t', table, '--data-only', '-f', '-', dump_path],
    capture_output=True,
  )
  rows = []
  in_copy = False
  for raw_line in io.BytesIO(result.stdout):
    line = raw_line.decode('utf-8', errors='replace')
    if line.startswith('COPY ') and 'FROM stdin' in line:
      in_copy = True
      continue
    if in_copy:
      if line.rstrip('\n') == '\\.':
        break
      rows.append(line.rstrip('\n').split('\t'))
  return rows


def load_user_map(dump_path: str) -> dict[int, str]:
  """Restituisce {user_id: nickname} dalla tabella user del dump."""
  rows = _pg_restore_table(dump_path, 'user')
  # colonne COPY: role, external_id, password, id, created_at, updated_at, nickname
  user_map = {}
  for cols in rows:
    if len(cols) < 7:
      continue
    try:
      user_id = int(cols[3])
      nickname = cols[6]
      user_map[user_id] = nickname
    except (ValueError, IndexError):
      continue
  return user_map


def load_log_rows(dump_path: str) -> list[tuple]:
  """Restituisce [(content, user_id, created_at), ...] dalla tabella log del dump."""
  rows = _pg_restore_table(dump_path, 'log')
  # colonne COPY: content, user_id, id, created_at, updated_at
  result = []
  for cols in rows:
    if len(cols) < 4:
      continue
    try:
      content = cols[0]
      user_id = int(cols[1])
      created_at_raw = cols[3]
      result.append((content, user_id, created_at_raw))
    except (ValueError, IndexError):
      continue
  return result


# ---------------------------------------------------------------------------
# Parsing del content
# ---------------------------------------------------------------------------

def _parse_content(content: str) -> tuple[dict | None, dict | None]:
  """Restituisce (request, response) gestendo i due formati storici."""
  if not content or content == '\\N':
    return None, None

  try:
    payload = json.loads(content)
  except (json.JSONDecodeError, TypeError):
    return None, None

  if not isinstance(payload, dict):
    return None, None

  # Formato nuovo: {"request": {...}, "response": {...}}
  if 'request' in payload or 'response' in payload:
    return payload.get('request'), payload.get('response')

  # Formato vecchio: {"path": "...", "method": "...", ...} → è già la request
  return payload, None


def _parse_timestamp(raw: str) -> datetime:
  raw = raw.strip()
  try:
    dt = datetime.fromisoformat(raw)
  except ValueError:
    dt = datetime.now(ROME_TZ)
  return dt.astimezone(ROME_TZ) if dt.tzinfo else ROME_TZ.localize(dt)


# ---------------------------------------------------------------------------
# Scrittura JSONL
# ---------------------------------------------------------------------------

def write_entry(log_dir: Path, user_id: int, nickname: str, created_at_raw: str, content: str) -> None:
  request, response = _parse_content(content)
  ts = _parse_timestamp(created_at_raw)

  entry = {
    'ts': ts.isoformat(),
    'user_id': user_id,
    'nickname': nickname,
    'request': request,
    'response': response,
  }

  month_dir = log_dir / ts.strftime('%Y-%m')
  month_dir.mkdir(parents=True, exist_ok=True)
  log_file = month_dir / f'{ts.strftime("%Y-%m-%d")}.jsonl'
  with open(log_file, 'a', encoding='utf-8') as f:
    f.write(json.dumps(entry, ensure_ascii=False, default=_serialize_default))
    f.write('\n')


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

LOG_DIR = Path('/mnt/STATIC_FOLDER_ITALCO/prod/logs')


DEFAULT_DUMP = Path(__file__).parent / '260613160037.dump'


if __name__ == '__main__':
  dump_path = os.environ.get('DUMP_FILE', str(DEFAULT_DUMP))
  if not Path(dump_path).exists():
    print(f'Errore: dump non trovato: {dump_path}', file=sys.stderr)
    sys.exit(1)

  log_dir = LOG_DIR
  log_dir.mkdir(parents=True, exist_ok=True)

  print('Caricamento mappa utenti…')
  user_map = load_user_map(dump_path)
  print(f'  {len(user_map)} utenti trovati')

  print('Caricamento righe log…')
  log_rows = load_log_rows(dump_path)
  print(f'  {len(log_rows)} righe trovate')

  skipped = 0
  for content, user_id, created_at_raw in tqdm(log_rows, desc='Scrittura JSONL'):
    nickname = user_map.get(user_id)
    if nickname is None:
      skipped += 1
      continue
    write_entry(log_dir, user_id, nickname, created_at_raw, content)

  if skipped:
    print(f'Attenzione: {skipped} righe saltate (user_id non trovato nella mappa)')

  print('Fatto.')

"""Bonifica le entry JSONL scritte con request/response null dalla migrazione
iniziale (bug: escape PostgreSQL COPY non decodificate prima del json.loads).

Legge il dump, ricostruisce la mappa ts→(request,response) e riscrive ogni
riga null con i dati corretti. Le entry runtime (non null) vengono lasciate
invariate. Gli indici .idx vengono rimossi e verranno ricostruiti dal reader.

Uso:
  [DUMP_FILE=...] python -m scripts.fix_log_nulls
"""

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
LOG_DIR = Path('/mnt/STATIC_FOLDER_ITALCO/prod/logs')
DEFAULT_DUMP = Path(__file__).parent / '260613160037.dump'


def _serialize_default(o):
  return float(o) if isinstance(o, decimal.Decimal) else str(o)


def _unescape_copy(value: str) -> str:
  return value.replace('\\n', '\n').replace('\\r', '\r').replace('\\t', '\t').replace('\\\\', '\\')


def _parse_timestamp(raw: str) -> datetime:
  raw = raw.strip()
  try:
    dt = datetime.fromisoformat(raw)
  except ValueError:
    dt = datetime.now(ROME_TZ)
  return dt.astimezone(ROME_TZ) if dt.tzinfo else ROME_TZ.localize(dt)


def _pg_restore_table(dump_path: str, table: str) -> list[list[str]]:
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


def _parse_content(content: str) -> tuple[dict | None, dict | None]:
  if not content or content == '\\N':
    return None, None
  try:
    payload = json.loads(_unescape_copy(content))
  except (json.JSONDecodeError, TypeError):
    return None, None
  if not isinstance(payload, dict):
    return None, None
  if 'request' in payload or 'response' in payload:
    return payload.get('request'), payload.get('response')
  return payload, None


def build_ts_map(dump_path: str) -> dict[str, tuple]:
  """Restituisce {ts_isoformat: (request, response)} per tutte le righe del dump."""
  rows = _pg_restore_table(dump_path, 'log')
  ts_map = {}
  for cols in rows:
    if len(cols) < 4:
      continue
    try:
      content = cols[0]
      created_at_raw = cols[3]
    except IndexError:
      continue
    ts = _parse_timestamp(created_at_raw).isoformat()
    request, response = _parse_content(content)
    ts_map[ts] = (request, response)
  return ts_map


def fix_jsonl(path: Path, ts_map: dict) -> int:
  """Riscrive il file sostituendo le righe null con i dati del dump.
  Restituisce il numero di righe corrette."""
  lines = path.read_bytes().splitlines(keepends=True)
  fixed = 0
  out_lines = []

  for raw in lines:
    raw_stripped = raw.strip()
    if not raw_stripped:
      out_lines.append(raw)
      continue

    try:
      entry = json.loads(raw_stripped)
    except (json.JSONDecodeError, ValueError):
      out_lines.append(raw)
      continue

    if entry.get('request') is None and entry.get('response') is None:
      ts = entry.get('ts')
      if ts and ts in ts_map:
        request, response = ts_map[ts]
        entry['request'] = request
        entry['response'] = response
        raw = (json.dumps(entry, ensure_ascii=False, default=_serialize_default) + '\n').encode('utf-8')
        fixed += 1

    out_lines.append(raw)

  tmp = path.with_suffix('.tmp')
  tmp.write_bytes(b''.join(out_lines))
  tmp.replace(path)

  # Rimuovi l'indice: offset cambiati, verrà ricostruito dal reader
  idx = path.with_suffix('.idx')
  if idx.exists():
    idx.unlink()

  return fixed


if __name__ == '__main__':
  dump_path = os.environ.get('DUMP_FILE', str(DEFAULT_DUMP))
  if not Path(dump_path).exists():
    print(f'Errore: dump non trovato: {dump_path}', file=sys.stderr)
    sys.exit(1)

  print('Costruzione mappa ts→(request,response) dal dump…')
  ts_map = build_ts_map(dump_path)
  print(f'  {len(ts_map)} entry nel dump')

  jsonl_files = sorted(LOG_DIR.glob('*/*.jsonl'))
  print(f'  {len(jsonl_files)} file JSONL da esaminare')

  total_fixed = 0
  for jsonl in tqdm(jsonl_files, desc='Bonifica JSONL'):
    total_fixed += fix_jsonl(jsonl, ts_map)

  print(f'Fatto. {total_fixed} righe corrette.')

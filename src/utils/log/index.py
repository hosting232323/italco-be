import json
from pathlib import Path

from .paths import INDEX_SUFFIX
from .serialization import parse_line


def index_path(jsonl: Path) -> Path:
  return jsonl.with_suffix(INDEX_SUFFIX)


def index_record(entry: dict, off: int) -> dict:
  request_info = entry.get('request') or {}
  response = entry.get('response')
  response = response if isinstance(response, dict) else {}
  return {
    'ts': entry.get('ts'),
    'user_id': entry.get('user_id'),
    'nickname': entry.get('nickname'),
    'status': response.get('status'),
    'method': request_info.get('method'),
    'path': request_info.get('path'),
    'off': off,
  }


def ensure_index(jsonl: Path) -> Path:
  """Costruisce/aggiorna l'indice gemello leggendo solo la coda non ancora indicizzata."""
  idx = index_path(jsonl)
  size = jsonl.stat().st_size
  start = 0

  if idx.exists():
    last = _last_index_record(idx)
    if last is not None and last.get('off') is not None and last['off'] < size:
      with open(jsonl, 'rb') as f:
        f.seek(last['off'])
        f.readline()  # consuma l'ultima riga già indicizzata
        start = f.tell()
    else:
      idx.unlink()  # indice incoerente o file ruotato/troncato: ricostruzione completa

  if start >= size:
    if not idx.exists():
      idx.touch()
    return idx

  with open(jsonl, 'rb') as src, open(idx, 'a', encoding='utf-8') as out:
    src.seek(start)
    off = start
    for line in src:
      entry = parse_line(line)
      if entry is not None:
        out.write(json.dumps(index_record(entry, off), ensure_ascii=False))
        out.write('\n')
      off += len(line)

  return idx


def read_index(idx: Path) -> list:
  records = []
  if not idx.exists():
    return records
  with open(idx, 'rb') as f:
    for line in f:
      line = line.strip()
      if not line:
        continue
      try:
        records.append(json.loads(line))
      except ValueError:
        continue
  return records


def read_entry(jsonl: Path, off: int):
  with open(jsonl, 'rb') as f:
    f.seek(off)
    line = f.readline()
  return parse_line(line)


def _last_index_record(idx: Path):
  last = None
  with open(idx, 'rb') as f:
    for line in f:
      line = line.strip()
      if line:
        try:
          last = json.loads(line)
        except ValueError:
          pass
  return last

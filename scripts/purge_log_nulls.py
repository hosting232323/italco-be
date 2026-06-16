"""Rimuove dai file JSONL tutte le righe con request e response null.

Uso:
  python -m scripts.purge_log_nulls
"""

import json
import sys
from pathlib import Path

from tqdm import tqdm


LOG_DIR = Path('/mnt/STATIC_FOLDER_ITALCO/prod/logs')


if __name__ == '__main__':
  jsonl_files = sorted(LOG_DIR.glob('*/*.jsonl'))
  total_removed = 0

  for path in tqdm(jsonl_files, desc='Pulizia JSONL'):
    lines = path.read_bytes().splitlines(keepends=True)
    kept = []
    removed = 0

    for raw in lines:
      stripped = raw.strip()
      if not stripped:
        continue
      try:
        entry = json.loads(stripped)
      except (json.JSONDecodeError, ValueError):
        kept.append(raw)
        continue

      if entry.get('request') is None and entry.get('response') is None:
        removed += 1
      else:
        kept.append(raw)

    if removed:
      tmp = path.with_suffix('.tmp')
      tmp.write_bytes(b''.join(kept))
      tmp.replace(path)

      idx = path.with_suffix('.idx')
      if idx.exists():
        idx.unlink()

      total_removed += removed

  print(f'Fatto. {total_removed} righe rimosse.', file=sys.stderr)

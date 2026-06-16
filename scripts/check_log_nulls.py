"""Scansiona i file JSONL e stampa le righe ancora con request e response null.

Uso:
  python -m scripts.check_log_nulls
"""

import json
import sys
from pathlib import Path

from tqdm import tqdm


LOG_DIR = Path('/mnt/STATIC_FOLDER_ITALCO/prod/logs')


if __name__ == '__main__':
  jsonl_files = sorted(LOG_DIR.glob('*/*.jsonl'))
  total = 0
  nulls = 0

  for path in tqdm(jsonl_files, desc='Scansione'):
    for raw in path.read_bytes().splitlines():
      raw = raw.strip()
      if not raw:
        continue
      total += 1
      try:
        entry = json.loads(raw)
      except (json.JSONDecodeError, ValueError):
        continue
      if entry.get('request') is None and entry.get('response') is None:
        nulls += 1
        print(json.dumps(entry, ensure_ascii=False))

  print(f'\nTotale righe: {total} — ancora null: {nulls}', file=sys.stderr)

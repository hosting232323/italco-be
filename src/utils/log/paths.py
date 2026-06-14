from pathlib import Path

from ... import STATIC_FOLDER, IS_DEV


LOG_DIR = Path(STATIC_FOLDER) / ('test' if IS_DEV else 'prod') / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOG_MAX_FIELD_CHARS = 50_000
LOG_MAX_LINE_BYTES = 1_000_000

# Estensione del file indice gemello (es. 2026-06-14.jsonl -> 2026-06-14.idx).
INDEX_SUFFIX = '.idx'

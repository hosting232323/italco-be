import os
import sys
from datetime import datetime

from api.storage import get_all_filenames
from database_api import Session, set_database
from database_api.operations import create
from src.database.schema import RaeDocument, DisposalDocument


STATIC_FOLDER = os.environ.get(
  'STATIC_FOLDER',
  os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static'),
)

# 233.pdf: DTR 39 di Idea Monopoli (rae_product 191), sostituito da 257.pdf il 02/07 dopo la bonifica.
# 14.pdf: owner da identificare aprendo il PDF, poi aggiungerlo qui.
KNOWN_OWNERS = {
  'rae_document': {'233.pdf': 191},
  'disposal_document': {},
}

CONFIG = [
  {'model': RaeDocument, 'owner_field': 'rae_product_id', 'subfolder': 'dtr-documents', 'label': 'DTR'},
  {'model': DisposalDocument, 'owner_field': 'disposal_id', 'subfolder': 'fir-documents', 'label': 'FIR'},
]


def link_prefix(rows) -> str | None:
  for row in rows:
    if row.link:
      return row.link[: row.link.rfind('/') + 1]
  return None


def reconcile(config: dict, apply: bool):
  model, owner_field, subfolder, label = config['model'], config['owner_field'], config['subfolder'], config['label']

  paths = {os.path.basename(path): path for path in get_all_filenames(STATIC_FOLDER, 'local', subfolder)}

  with Session() as session:
    rows = session.query(model).all()

  linked = {os.path.basename(row.link) for row in rows}
  prefix = link_prefix(rows)
  known = KNOWN_OWNERS.get(model.__tablename__, {})

  orphans = sorted(set(paths) - linked)
  missing = sorted(linked - set(paths))

  print(f'\n=== {label} ({subfolder}) ===')
  print(f'  files su disco: {len(paths)} | righe: {len(rows)} | files orfani: {len(orphans)} | righe senza file: {len(missing)}')

  for name in missing:
    print(f'  ! riga senza file su disco: {name}')

  if orphans and prefix is None:
    print('  ✗ nessuna riga esistente da cui ricavare il prefisso del link, gruppo saltato')
    return

  for name in orphans:
    owner = known.get(name)
    created_at = datetime.fromtimestamp(os.path.getmtime(paths[name]))
    if apply:
      create(model, {'link': prefix + name, owner_field: owner, 'created_at': created_at})
      print(f'  + importato {name} ({owner_field}={owner}, created_at={created_at})')
    else:
      print(f'  [dry-run] importerei {name} ({owner_field}={owner}, created_at={created_at}) come {prefix + name}')


if __name__ == '__main__':
  apply = '--apply' in sys.argv
  set_database(os.environ['DATABASE_URL'])

  for config in CONFIG:
    reconcile(config, apply)

  if not apply:
    print('\nDry run. Rilancia con --apply per inserire le righe.')

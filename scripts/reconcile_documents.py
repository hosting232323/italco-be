import os
from datetime import datetime

from api.storage import get_all_filenames
from api.storage.utils import get_full_path
from database_api import Session, set_database
from database_api.operations import create
from src.database.schema import RaeDocument, DisposalFirstCopyDocument, DisposalFourthCopyDocument


STATIC_FOLDER = os.environ.get(
  'STATIC_FOLDER',
  os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static'),
)

# 233.pdf: DTR 39 di Idea Monopoli (rae_product 191), sostituito da 257.pdf il 02/07 dopo la bonifica.
# 14.pdf: primo tentativo fallito dell'upload del DTR di rae_product 153 (identico a 15.pdf).
KNOWN_OWNERS = {
  'rae_document': {'233.pdf': 191, '14.pdf': 153},
  'disposal_first_copy_document': {},
  'disposal_fourth_copy_document': {},
}

CONFIG = [
  {'model': RaeDocument, 'owner_field': 'rae_product_id', 'subfolder': 'dtr-documents', 'label': 'DTR'},
  {
    'model': DisposalFirstCopyDocument,
    'owner_field': 'disposal_id',
    'subfolder': 'first-copy-fir-documents',
    'label': 'First Copy FIR',
  },
  {
    'model': DisposalFourthCopyDocument,
    'owner_field': 'disposal_id',
    'subfolder': 'fourth-copy-fir-documents',
    'label': 'Fourth Copy FIR',
  },
]


def link_prefix(rows) -> str | None:
  for row in rows:
    if row.link:
      return row.link[: row.link.rfind('/') + 1]
  return None


def reconcile(config: dict):
  model, owner_field, subfolder, label = config['model'], config['owner_field'], config['subfolder'], config['label']

  os.makedirs(get_full_path(STATIC_FOLDER, subfolder, False), exist_ok=True)
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
    create(model, {'link': prefix + name, owner_field: owner, 'created_at': created_at})
    print(f'  + importato {name} ({owner_field}={owner}, created_at={created_at})')


if __name__ == '__main__':
  set_database(os.environ['DATABASE_URL'])

  for config in CONFIG:
    reconcile(config)

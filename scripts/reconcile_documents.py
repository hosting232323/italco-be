# ruff: noqa: E402, T201
import argparse
import os
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
  sys.path.insert(0, str(PROJECT_ROOT))

from api.storage import get_all_filenames, get_full_path
from database_api import Session, set_database
from database_api.operations import create

from src.database.schema import FirFirstDocument, FirFourthDocument, DtrDocument


STATIC_FOLDER = os.environ.get(
  'STATIC_FOLDER',
  os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static'),
)

# 233.pdf: DTR 39 di Idea Monopoli (rae_product 191), sostituito da 257.pdf il 02/07 dopo la bonifica.
# 14.pdf: primo tentativo fallito dell'upload del DTR di rae_product 153 (identico a 15.pdf).
KNOWN_OWNERS = {
  'dtr_document': {'233.pdf': 191, '14.pdf': 153},
  'fir_first_document': {},
  'fir_fourth_document': {},
}

CONFIG = [
  {'model': DtrDocument, 'owner_field': 'rae_product_id', 'subfolder': 'dtr-documents', 'label': 'DTR'},
  {
    'model': FirFirstDocument,
    'owner_field': 'disposal_id',
    'subfolder': 'fir-first-document',
    'label': 'First Copy FIR',
    'owner_required': True,
  },
  {
    'model': FirFourthDocument,
    'owner_field': 'disposal_id',
    'subfolder': 'fir-fourth-document',
    'label': 'Fourth Copy FIR',
    'owner_required': True,
  },
]


def link_prefix(rows) -> str | None:
  for row in rows:
    if row.link and '/' in row.link:
      return row.link.rsplit('/', 1)[0] + '/'
  return None


def reconcile(
  config: dict,
  *,
  static_folder: str = STATIC_FOLDER,
  known_owners: dict | None = None,
  apply: bool = False,
) -> dict:
  model = config['model']
  owner_field = config['owner_field']
  subfolder = config['subfolder']
  label = config['label']
  owner_required = config.get('owner_required', False)

  storage_folder = get_full_path(static_folder, subfolder, False)
  os.makedirs(storage_folder, exist_ok=True)
  paths = {os.path.basename(path): path for path in get_all_filenames(static_folder, subfolder=subfolder)}

  with Session() as session:
    rows = session.query(model).all()
    linked = {os.path.basename(row.link) for row in rows if row.link}
    prefix = link_prefix(rows)
    owners_by_table = KNOWN_OWNERS if known_owners is None else known_owners
    owners = owners_by_table.get(model.__tablename__, {})
    orphans = sorted(set(paths) - linked)
    missing = sorted(linked - set(paths))

    report = {
      'label': label,
      'files': len(paths),
      'rows': len(rows),
      'orphans': orphans,
      'missing': missing,
      'imported': [],
      'unresolved': [],
      'applied': apply,
    }

    print(f'\n=== {label} ({subfolder}) ===')
    print(
      f'  files su disco: {len(paths)} | righe: {len(rows)} | '
      f'files orfani: {len(orphans)} | righe senza file: {len(missing)}'
    )

    for name in missing:
      print(f'  ! riga senza file su disco: {name}')

    if orphans and prefix is None:
      print('  x nessuna riga esistente da cui ricavare il prefisso del link, gruppo saltato')
      report['skipped_reason'] = 'missing_link_prefix'
      return report

    for name in orphans:
      owner = owners.get(name)
      if owner_required and owner is None:
        report['unresolved'].append(name)
        print(f'  x {name} saltato: {owner_field} obbligatorio e non risolto')
        continue

      created_at = datetime.fromtimestamp(os.path.getmtime(paths[name])).astimezone()
      action = 'importato' if apply else 'da importare'
      print(f'  + {action} {name} ({owner_field}={owner}, created_at={created_at.isoformat()})')

      if apply:
        create(
          model,
          {'link': prefix + name, owner_field: owner, 'created_at': created_at},
          session=session,
        )
        report['imported'].append(name)

    if apply:
      session.commit()

    return report


def parse_args():
  parser = argparse.ArgumentParser(description='Riconcilia i documenti presenti su disco con le righe nel database.')
  parser.add_argument(
    '--apply',
    action='store_true',
    help="Applica gli inserimenti. Senza questa opzione viene eseguita solo un'anteprima.",
  )
  return parser.parse_args()


if __name__ == '__main__':
  args = parse_args()
  set_database(os.environ['DATABASE_URL'])

  if not args.apply:
    print('DRY RUN: nessuna modifica al database. Usa --apply per applicare la bonifica.')

  for item in CONFIG:
    reconcile(item, apply=args.apply)

# ruff: noqa: E402, T201
"""Ri-hasha con werkzeug tutte le password legacy (AES) rimaste nel database.

Sostituisce la migrazione "al primo login" in end_points/users/__init__.py:
una volta eseguito su tutti gli ambienti, quel percorso e LEGACY_PASSWORD_*
possono essere rimossi dal backend.
"""
import argparse
import base64
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
  sys.path.insert(0, str(PROJECT_ROOT))

from api.users.security import hash_password, is_hashed
from database_api import Session, set_database
from database_api.operations import update

from src.database.schema import User


LEGACY_PASSWORD_SECRET_KEY = os.environ['LEGACY_PASSWORD_SECRET_KEY']
LEGACY_PASSWORD_IV = os.environ['LEGACY_PASSWORD_IV']


def legacy_decrypt(stored: str) -> str:
  """Inversa di legacy_encrypt (end_points/users/legacy.py): stessa chiave/IV, AES-CBC."""
  key_bytes = LEGACY_PASSWORD_SECRET_KEY.encode('utf-8')
  iv_bytes = LEGACY_PASSWORD_IV.encode('utf-8')

  raw = base64.b64decode(stored)
  ciphertext = raw[len(iv_bytes):]

  decryptor = Cipher(algorithms.AES(key_bytes), modes.CBC(iv_bytes)).decryptor()
  padded = decryptor.update(ciphertext) + decryptor.finalize()
  unpadder = padding.PKCS7(128).unpadder()
  return (unpadder.update(padded) + unpadder.finalize()).decode('utf-8')


def migrate_legacy_passwords(*, apply: bool) -> dict:
  report = {'migrated': [], 'already_hashed': 0, 'no_password': 0, 'failed': []}

  with Session() as session:
    users = session.query(User).all()
    for user in users:
      if not user.password:
        report['no_password'] += 1
        continue
      if is_hashed(user.password):
        report['already_hashed'] += 1
        continue

      try:
        plaintext = legacy_decrypt(user.password)
      except Exception as e:
        report['failed'].append(user.id)
        print(f'  x utente {user.id} ({user.nickname}): decrittografia fallita ({e})')
        continue

      action = 'migrata' if apply else 'da migrare'
      print(f'  + password {action} per utente {user.id} ({user.nickname})')
      if apply:
        update(user, {'password': hash_password(plaintext)}, session=session)
      report['migrated'].append(user.id)

    if apply:
      session.commit()

  return report


def parse_args():
  parser = argparse.ArgumentParser(
    description='Ri-hasha con werkzeug tutte le password legacy (AES) ancora presenti nel database.'
  )
  parser.add_argument(
    '--apply',
    action='store_true',
    help="Applica gli aggiornamenti. Senza questa opzione viene eseguita solo un'anteprima.",
  )
  return parser.parse_args()


if __name__ == '__main__':
  args = parse_args()
  set_database(os.environ['DATABASE_URL'])

  if not args.apply:
    print('DRY RUN: nessuna modifica al database. Usa --apply per applicare la migrazione.')

  result = migrate_legacy_passwords(apply=args.apply)
  print(
    f'\nTotale: {len(result["migrated"])} {"migrate" if args.apply else "da migrare"}, '
    f'{result["already_hashed"]} già su hash, {result["no_password"]} senza password, '
    f'{len(result["failed"])} falliti.'
  )

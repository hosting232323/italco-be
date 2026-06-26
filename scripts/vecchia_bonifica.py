"""Bonifica delle date/stati dei DTR (rae_product) per i punti vendita Euronics.

Lo script e' DIFENSIVO: il database locale e' solo di test e i dati in produzione
possono differire. Per questo ogni correzione viene validata contro lo stato reale
della riga e tutti i prodotti rae "problematici" (non trovati, ambigui, in uno stato
inatteso, oppure che richiedono una decisione manuale) vengono MESSI DA PARTE in un
report invece di essere modificati alla cieca.

Uso:
  # anteprima (DRY-RUN, nessuna modifica scritta): default
  python -m scripts.rae_dtr_bonifica

  # applica davvero le modifiche
  python -m scripts.rae_dtr_bonifica --apply

Richiede la variabile d'ambiente DATABASE_URL (come gli altri script).
"""

import os
import sys
import argparse
from datetime import date, datetime

from sqlalchemy import func

from database_api import set_database, Session
from src.database.enum import RaeStatus
from src.database.schema import RaeProduct, User


# Tipi di operazione
DATE = 'date'  # cambia SOLO dtr_date (solo se NON e' ancora GENERATO)
DELETE = 'delete'  # elimina del tutto il rae_product (solo se e' GENERATO)


def d(iso: str) -> date:
  return datetime.strptime(iso, '%Y-%m-%d').date()


# Elenco delle bonifiche richieste.
# (nickname punto vendita, numero DTR, tipo operazione, data target)
CORRECTIONS = [
  # --- EURONICS MOLFETTA ---
  ('Euronics Molfetta', 2, DATE, d('2026-04-02')),
  ('Euronics Molfetta', 15, DATE, d('2026-04-14')),
  ('Euronics Molfetta', 23, DATE, d('2026-04-16')),
  # --- EURONICS CORATO ---
  ('Euronics Corato', 8, DELETE, None),
  # --- EURONICS BARI MAX ---
  ('Euronics Bari Max', 5, DATE, d('2026-04-02')),
  ('Euronics Bari Max', 10, DATE, d('2026-04-03')),
  ('Euronics Bari Max', 11, DATE, d('2026-04-03')),
  ('Euronics Bari Max', 13, DATE, d('2026-04-03')),
  ('Euronics Bari Max', 15, DATE, d('2026-04-07')),
  ('Euronics Bari Max', 16, DATE, d('2026-04-07')),
  ('Euronics Bari Max', 35, DATE, d('2026-04-13')),
  # --- EURONICS SANTA CATERINA ---
  ('Euronics Santa Caterina', 5, DATE, d('2026-04-02')),
  ('Euronics Santa Caterina', 16, DATE, d('2026-04-07')),
  ('Euronics Santa Caterina', 17, DATE, d('2026-04-07')),
  ('Euronics Santa Caterina', 18, DATE, d('2026-04-07')),
  ('Euronics Santa Caterina', 19, DATE, d('2026-04-07')),
  ('Euronics Santa Caterina', 20, DATE, d('2026-04-07')),
  ('Euronics Santa Caterina', 21, DATE, d('2026-04-07')),
  ('Euronics Santa Caterina', 22, DATE, d('2026-04-07')),
  ('Euronics Santa Caterina', 23, DATE, d('2026-04-07')),
  ('Euronics Santa Caterina', 24, DATE, d('2026-04-07')),
  # 39 e 42: solo cambio data (lo stato ANNULLED NON viene toccato, come richiesto).
  ('Euronics Santa Caterina', 39, DATE, d('2026-04-16')),
  ('Euronics Santa Caterina', 42, DATE, d('2026-04-16')),
  # 52: ritiro da eliminare (verra' eliminato solo se GENERATO).
  ('Euronics Santa Caterina', 52, DELETE, None),
]


def resolve_user(session, nickname: str):
  users = session.query(User).filter(func.lower(User.nickname) == nickname.lower()).all()
  if len(users) == 0:
    return None, f'punto vendita "{nickname}" non trovato'
  if len(users) > 1:
    return None, f'punto vendita "{nickname}" ambiguo ({len(users)} utenti)'
  return users[0], None


def resolve_product(session, user: User, number: int):
  products = session.query(RaeProduct).filter(RaeProduct.user_id == user.id, RaeProduct.number == number).all()
  if len(products) == 0:
    return None, f'DTR {number} non trovato'
  if len(products) > 1:
    return (
      None,
      f'DTR {number} ambiguo ({len(products)} prodotti rae con lo stesso numero: ids {[p.id for p in products]})',
    )
  return products[0], None


def plan_change(product: RaeProduct, kind: str, target_date):
  """Decide cosa fare. Ritorna (changes_dict, reason_to_set_aside).

  Se reason_to_set_aside e' valorizzato il prodotto va MESSO DA PARTE e non modificato.
  changes_dict e' del tipo {campo: (valore_attuale, valore_nuovo)}.
  """
  if kind == DELETE:
    # Eliminazione: si elimina solo se e' GENERATO, altrimenti messo da parte.
    if product.status != RaeStatus.GENERATED:
      return None, f'eliminazione richiesta ma stato {product.status.value} (non GENERATO): verifica manuale'
    return None, None

  if kind == DATE:
    # Cambio data: possibile solo se NON e' piu' GENERATO, altrimenti messo da parte.
    if product.status == RaeStatus.GENERATED:
      return None, 'ancora GENERATO: impossibile correggere la data, verifica manuale'
    changes = {'dtr_date': (product.dtr_date, target_date)}
    return changes, None

  return None, f'tipo operazione sconosciuto: {kind}'


def fmt(value):
  if isinstance(value, RaeStatus):
    return value.value
  return str(value)


def main(apply: bool):
  set_database(os.environ['DATABASE_URL'])

  applied = []
  deleted = []
  set_aside = []

  with Session() as session:
    for nickname, number, kind, target_date in CORRECTIONS:
      label = f'{nickname} - DTR {number}'

      user, err = resolve_user(session, nickname)
      if err:
        set_aside.append((label, kind, err))
        continue

      product, err = resolve_product(session, user, number)
      if err:
        set_aside.append((label, kind, err))
        continue

      changes, reason = plan_change(product, kind, target_date)
      if reason:
        detail = f'{reason} (rae_product id {product.id}, stato {product.status.value}, dtr_date {product.dtr_date})'
        set_aside.append((label, kind, detail))
        continue

      if kind == DELETE:
        detail = f'stato {product.status.value}, dtr_date {product.dtr_date}'
        deleted.append((label, product.id, detail))
        session.delete(product)
        continue

      # Applica le modifiche sull'oggetto in sessione
      for field, (_old, new) in changes.items():
        setattr(product, field, new)

      diff = ', '.join(f'{f}: {fmt(old)} -> {fmt(new)}' for f, (old, new) in changes.items())
      applied.append((label, product.id, diff))

    if apply:
      session.commit()
    else:
      session.rollback()

  _print_report(applied, deleted, set_aside, apply)


def _print_report(applied, deleted, set_aside, apply: bool):
  mode = 'APPLICATO' if apply else 'DRY-RUN (nessuna modifica scritta)'
  print('=' * 78)
  print(f'BONIFICA DTR EURONICS - modalita: {mode}')
  print('=' * 78)

  print(f'\n## CORREZIONI {"APPLICATE" if apply else "DA APPLICARE"} ({len(applied)})')
  if applied:
    for label, rae_id, diff in applied:
      print(f'  [OK] {label} (rae_product id {rae_id}) -> {diff}')
  else:
    print('  (nessuna)')

  print(f'\n## ELIMINAZIONI {"ESEGUITE" if apply else "DA ESEGUIRE"} ({len(deleted)})')
  if deleted:
    for label, rae_id, detail in deleted:
      print(f'  [DEL] {label} (rae_product id {rae_id}) -> {detail}')
  else:
    print('  (nessuna)')

  print(f'\n## MESSI DA PARTE / DA VERIFICARE MANUALMENTE ({len(set_aside)})')
  if set_aside:
    for label, kind, detail in set_aside:
      print(f'  [!] {label} [{kind}]: {detail}')
  else:
    print('  (nessuno)')

  print('\n' + '=' * 78)
  if not apply:
    print('DRY-RUN: rilancia con --apply per scrivere le modifiche sopra elencate.')
  print('=' * 78)


if __name__ == '__main__':
  parser = argparse.ArgumentParser(description='Bonifica date/stati DTR Euronics (rae_product).')
  parser.add_argument('--apply', action='store_true', help='applica e committa le modifiche (default: dry-run)')
  args = parser.parse_args()

  if 'DATABASE_URL' not in os.environ:
    print("ERRORE: variabile d'ambiente DATABASE_URL non impostata.", file=sys.stderr)
    sys.exit(1)

  main(args.apply)

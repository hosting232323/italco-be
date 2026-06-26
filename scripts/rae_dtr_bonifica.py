"""Bonifica delle date/stati dei DTR (rae_product) dei punti vendita.

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
from src.database.schema import Product, RaeProduct, User


# Tipi di operazione
DATE = 'date'  # cambia SOLO dtr_date (la data stampata sul DTR; solo se NON e' GENERATO)
STATUS = 'status'  # cambia lo stato (solo se la riga e' nello stato di partenza atteso)
DELETE = 'delete'  # elimina del tutto il rae_product (solo se e' GENERATO)


def d(iso: str) -> date:
  return datetime.strptime(iso, '%Y-%m-%d').date()


# Elenco delle bonifiche richieste.
# (nickname punto vendita, numero DTR, tipo operazione, payload)
#   - DATE:   payload = data target (dtr_date)
#   - STATUS: payload = (stato_atteso, stato_target, hint_prodotto_da_ricollegare|None)
#             Se hint_prodotto e' valorizzato, oltre a cambiare stato si ripristina il
#             collegamento Product.rae_product_id verso questo rae: ogni ritiro LDR deve
#             essere agganciato a una riga prodotto dell'ordine (invariante del DB).
#   - DELETE: payload = None
CORRECTIONS = [
  # --- IDEA MONOPOLI (ragione sociale: DR TRADE S.R.L.) ---
  # DTR 39, a nome Svezia Manuel: il RAEE e' stato ritirato ma il DTR risulta
  # Annullato. Va riportato in stato LDR e ricollegato alla sua riga prodotto
  # (lavatrice Candy BC4S69M6D8J-S), rimasta orfana dopo l'annullamento.
  ('Idea Monopoli', 39, STATUS, (RaeStatus.ANNULLED, RaeStatus.LDR, 'BC4S69M6D8J-S')),
  # DTR 56, a nome Svezia Manuel: correzione della data di emissione stampata sul
  # DTR (campo dtr_date) da 22/05/26 a 03/06/26.
  ('Idea Monopoli', 56, DATE, d('2026-06-03')),
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


def plan_reconnect(session, rae_product: RaeProduct, hint: str):
  """Individua la riga prodotto dell'ordine da ricollegare a questo rae.

  Ritorna (product_da_collegare, reason). Se entrambi sono None il rae e' gia
  collegato a una riga prodotto: nulla da fare. Per sicurezza l'aggancio avviene
  solo se la corrispondenza e' univoca (una sola riga libera che matcha l'hint).
  """
  already = session.query(Product).filter(Product.rae_product_id == rae_product.id).first()
  if already:
    return None, None

  candidates = (
    session.query(Product)
    .filter(
      Product.order_id == rae_product.order_id,
      Product.rae_product_id.is_(None),
      func.lower(Product.name).like(f'%{hint.lower()}%'),
    )
    .all()
  )
  if len(candidates) == 0:
    return None, f'nessuna riga prodotto libera su ordine {rae_product.order_id} corrisponde a "{hint}": verifica manuale'
  if len(candidates) > 1:
    return (
      None,
      f'collegamento ambiguo: {len(candidates)} righe prodotto libere corrispondono a "{hint}" '
      f'(ids {[c.id for c in candidates]}): verifica manuale',
    )
  return candidates[0], None


def plan_change(session, product: RaeProduct, kind: str, payload):
  """Decide cosa fare. Ritorna (changes_dict, product_da_collegare, reason).

  Se reason e' valorizzato il prodotto va MESSO DA PARTE e non modificato.
  changes_dict e' del tipo {campo: (valore_attuale, valore_nuovo)} sul rae_product.
  product_da_collegare, se presente, e' la riga prodotto da riagganciare al rae.
  """
  if kind == DELETE:
    # Eliminazione: si elimina solo se e' GENERATO, altrimenti messo da parte.
    if product.status != RaeStatus.GENERATED:
      return None, None, f'eliminazione richiesta ma stato {product.status.value} (non GENERATO): verifica manuale'
    return None, None, None

  if kind == DATE:
    # Cambio data: possibile solo se NON e' piu' GENERATO, altrimenti messo da parte.
    if product.status == RaeStatus.GENERATED:
      return None, None, 'ancora GENERATO: impossibile correggere la data, verifica manuale'
    if product.dtr_date == payload:
      return None, None, f'dtr_date gia {payload}: nessuna modifica necessaria'
    return {'dtr_date': (product.dtr_date, payload)}, None, None

  if kind == STATUS:
    # Cambio stato (e, se richiesto, ripristino del collegamento con l'ordine).
    expected_from, target, reconnect_hint = payload

    changes = {}
    if product.status == target:
      pass  # stato gia corretto: resta da verificare solo il collegamento
    elif product.status == expected_from:
      changes['status'] = (product.status, target)
    else:
      return (
        None,
        None,
        f'atteso stato {expected_from.value} per passare a {target.value}, '
        f'ma trovato {product.status.value}: verifica manuale',
      )

    product_link = None
    if reconnect_hint:
      product_link, reason = plan_reconnect(session, product, reconnect_hint)
      if reason:
        return None, None, reason

    if not changes and product_link is None:
      return None, None, f'gia in stato {target.value} e gia collegato all\'ordine: nessuna modifica necessaria'

    return (changes or None), product_link, None

  return None, None, f'tipo operazione sconosciuto: {kind}'


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
    for nickname, number, kind, payload in CORRECTIONS:
      label = f'{nickname} - DTR {number}'

      user, err = resolve_user(session, nickname)
      if err:
        set_aside.append((label, kind, err))
        continue

      product, err = resolve_product(session, user, number)
      if err:
        set_aside.append((label, kind, err))
        continue

      changes, product_link, reason = plan_change(session, product, kind, payload)
      if reason:
        detail = f'{reason} (rae_product id {product.id}, stato {product.status.value}, dtr_date {product.dtr_date})'
        set_aside.append((label, kind, detail))
        continue

      if kind == DELETE:
        detail = f'stato {product.status.value}, dtr_date {product.dtr_date}'
        deleted.append((label, product.id, detail))
        session.delete(product)
        continue

      diff_parts = []

      # Modifiche sul rae_product (stato e/o data)
      for field, (old, new) in (changes or {}).items():
        setattr(product, field, new)
        diff_parts.append(f'{field}: {fmt(old)} -> {fmt(new)}')

      # Ripristino del collegamento con la riga prodotto dell'ordine
      if product_link is not None:
        old_link = product_link.rae_product_id
        product_link.rae_product_id = product.id
        diff_parts.append(f'product {product_link.id}.rae_product_id: {fmt(old_link)} -> {product.id}')

      applied.append((label, product.id, ', '.join(diff_parts)))

    if apply:
      session.commit()
    else:
      session.rollback()

  _print_report(applied, deleted, set_aside, apply)


def _print_report(applied, deleted, set_aside, apply: bool):
  mode = 'APPLICATO' if apply else 'DRY-RUN (nessuna modifica scritta)'
  print('=' * 78)
  print(f'BONIFICA DTR - modalita: {mode}')
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
  parser = argparse.ArgumentParser(description='Bonifica date/stati DTR (rae_product).')
  parser.add_argument('--apply', action='store_true', help='applica e committa le modifiche (default: dry-run)')
  args = parser.parse_args()

  if 'DATABASE_URL' not in os.environ:
    print("ERRORE: variabile d'ambiente DATABASE_URL non impostata.", file=sys.stderr)
    sys.exit(1)

  main(args.apply)

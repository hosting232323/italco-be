# ruff: noqa: E402, T201
"""Allinea il veicolo dei borderò pregressi ai corrieri che li facevano (delivery_group).

I corrieri di un borderò sono quelli di delivery_group, il veicolo di ogni corriere è
delivery_user_info.transport_id. Se i corrieri di uno stesso borderò stanno su veicoli
diversi, il veicolo del borderò è ambiguo:
  - borderò più vecchi di --months mesi: si sceglie a caso uno dei veicoli dei suoi corrieri;
  - borderò recenti: non si toccano, vengono solo elencati e contati.

Va lanciato dopo che delivery_user_info.transport_id è stata valorizzata e prima che
delivery_group venga eliminata.
"""
import argparse
import os
import random
import sys
from datetime import date
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
  sys.path.insert(0, str(PROJECT_ROOT))

from database_api import Session, set_database
from sqlalchemy import text


SCHEDULE_VEHICLES_QUERY = text(
  """
  SELECT s.id, s.date, s.transport_id,
         array_agg(DISTINCT d.transport_id) FILTER (WHERE d.transport_id IS NOT NULL) AS transport_ids,
         count(DISTINCT g.user_id) FILTER (WHERE d.transport_id IS NULL) AS users_without_vehicle
  FROM schedule s
  JOIN delivery_group g ON g.schedule_id = s.id
  LEFT JOIN delivery_user_info d ON d.user_id = g.user_id
  GROUP BY s.id
  ORDER BY s.date, s.id
  """
)


def months_ago(today: date, months: int) -> date:
  index = today.year * 12 + today.month - 1 - months
  year, month = divmod(index, 12)
  day = min(today.day, 28)
  return date(year, month + 1, day)


def reconcile_schedule_vehicles(*, months: int, apply: bool, seed: int = None) -> dict:
  cutoff = months_ago(date.today(), months)
  rng = random.Random(seed)
  report = {
    'cutoff': cutoff,
    'ambiguous_old': [],
    'ambiguous_recent': [],
    'single_other_vehicle': 0,
    'consistent': 0,
    'without_vehicle': 0,
  }

  with Session() as session:
    for schedule_id, schedule_date, current, transport_ids, _ in session.execute(SCHEDULE_VEHICLES_QUERY):
      if not transport_ids:
        report['without_vehicle'] += 1
      elif len(transport_ids) == 1:
        report['consistent' if transport_ids[0] == current else 'single_other_vehicle'] += 1
      elif schedule_date < cutoff:
        chosen = rng.choice(transport_ids)
        action = 'assegnato' if apply else 'da assegnare'
        print(f'  + borderò {schedule_id} del {schedule_date}: veicoli {transport_ids}, {action} {chosen}')
        if apply:
          session.execute(
            text('UPDATE schedule SET transport_id = :transport_id WHERE id = :id'),
            {'transport_id': chosen, 'id': schedule_id},
          )
        report['ambiguous_old'].append(schedule_id)
      else:
        print(f'  ! borderò {schedule_id} del {schedule_date}: veicoli {transport_ids}, attuale {current}, non toccato')
        report['ambiguous_recent'].append(schedule_id)

    if apply:
      session.commit()

  return report


def parse_args():
  parser = argparse.ArgumentParser(
    description='Sceglie il veicolo dei borderò pregressi i cui corrieri stanno su più veicoli.'
  )
  parser.add_argument('--months', type=int, default=2, help='Anzianità minima in mesi per correggere un borderò.')
  parser.add_argument('--seed', type=int, help='Seme della scelta casuale, per ripetere lo stesso risultato.')
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
    print('DRY RUN: nessuna modifica al database. Usa --apply per applicare la bonifica.')

  result = reconcile_schedule_vehicles(months=args.months, apply=args.apply, seed=args.seed)
  print(
    f'\nSoglia: borderò prima del {result["cutoff"]}.\n'
    f'Veicolo ambiguo, vecchi: {len(result["ambiguous_old"])} {"corretti" if args.apply else "da correggere"}.\n'
    f'Veicolo ambiguo, recenti: {len(result["ambiguous_recent"])} (non toccati).\n'
    f'Un solo veicolo, diverso da quello attuale: {result["single_other_vehicle"]}.\n'
    f'Coerenti: {result["consistent"]}. Corrieri senza veicolo: {result["without_vehicle"]}.'
  )

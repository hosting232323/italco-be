# ruff: noqa: T201
"""Profilo di una chiamata a /check-constraints: query per tabella e funzioni piu' costose.

Riusa Nominatim/OSRM finti e il database di scripts.stress_planning:

  python -m scripts.profile_check_constraints [--flag]
"""

import cProfile
import pstats
import random
import re
import sys
from collections import Counter

from sqlalchemy import event

import database_api
from scripts import stress_planning as sp

statements = Counter()


@event.listens_for(database_api.engine, 'before_cursor_execute')
def _collect(_connection, _cursor, statement, *_):
  table = re.search(r'FROM\s+"?(\w+)"?', statement, re.I)
  kind = statement.strip().split()[0].upper()
  statements[f'{kind} {table.group(1) if table else "?"}'] += 1


def main():
  random.seed(7)
  templates = sp.load_templates()
  template = random.choice([t for t in templates if t.cap])
  client = sp.app.test_client()
  report = sp.Report()
  sp.NET.latency = 0.02
  sp.call(
    client, report, 'warm', 'post', '/check-constraints', sp.token_for(template.user_id), sp.check_payload(template)
  )
  statements.clear()
  sp.NET.reset()
  profiler = cProfile.Profile()
  profiler.enable()
  status, body = sp.call(
    client, report, 'check', 'post', '/check-constraints', sp.token_for(template.user_id), sp.check_payload(template)
  )
  profiler.disable()
  print(f'cap={template.cap} http={status} giorni={len(body.get("dates", []))} esterne={dict(sp.NET.snapshot())}')
  print(f'query totali: {sum(statements.values())}')
  for name, count in statements.most_common(12):
    print(f'  {count:6} {name}')
  print("\nfunzioni piu' costose (tempo cumulato, solo codice src/):")
  stats = pstats.Stats(profiler, stream=sys.stdout)
  stats.sort_stats('cumulative').print_stats(r'src/', 14)


if __name__ == '__main__':
  main()

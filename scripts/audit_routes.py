# ruff: noqa: T201
"""Audit di tutte le rotte HTTP su una copia del database.

Per ogni rotta e metodo chiama l'app (Flask test client) senza token, con un token
non valido e con un token per ciascun ruolo, con parametri di percorso reali,
inesistenti e malformati e con payload vuoto/malformato. Riporta:

  - 5xx (eccezioni non gestite: input che non deve mai far esplodere il server)
  - rotte raggiungibili senza token (da confrontare con l'elenco di quelle pubbliche)
  - isolamento tra company: un admin della company B che legge/scrive risorse della A

Va lanciato su una copia del dump, mai in produzione, e senza rete verso l'esterno
(le rotte che mandano SMS/email provano a chiamare servizi veri):

  python -m scripts.audit_routes
"""

import json
import os
import re
import sys
import tempfile
from collections import Counter, defaultdict
from types import SimpleNamespace

from dotenv import load_dotenv

if 'DATABASE_URL' not in os.environ:
  sys.exit('DATABASE_URL obbligatoria: punta a una copia del dump, mai alla produzione')
load_dotenv('.env.test')
os.environ.setdefault('STATIC_FOLDER', tempfile.mkdtemp(prefix='italco-audit-static-'))

from sqlalchemy import text  # noqa: E402

import api.hooks as api_hooks  # noqa: E402
import database_api  # noqa: E402
import src.__main__  # noqa: E402,F401
from src import app  # noqa: E402
from src.database.enum import UserRole  # noqa: E402
from src.end_points.users.session import create_jwt_token  # noqa: E402

# Rotte che non ha senso colpire in massa: backup/ripristino toccano il disco e i servizi esterni.
SKIP = re.compile(r'^/(static|backup|chatty)(/|$)')
BAD_VALUES = ['abc', '-1', '99999999999999999999', "1' OR '1'='1"]
IGNORED_EXCEPTIONS = {'NotFound', 'Forbidden', 'Unauthorized', 'BadRequest', 'MethodNotAllowed', 'UnsupportedMediaType'}
BODIES = [{}, {'id': None}, {'products': 'x', 'dpc': 'not-a-date', 'cap': 123}, [1, 2, 3]]


class TracebackCapture:
  """Raccoglie i traceback che l'handler globale di generic-lib manderebbe a Telegram.

  L'handler trasforma ogni eccezione non gestita in HTTP 200 con {"status": "ko",
  "message": "Errore generico"}: dal codice HTTP non si vedono, e in produzione
  ognuna e' un messaggio Telegram. Qui nessuna notifica parte.
  """

  def __init__(self):
    self.tracebacks = []

  def __call__(self, traceback_text):
    self.tracebacks.append(traceback_text)

  def take(self):
    taken, self.tracebacks = self.tracebacks, []
    return taken


CAPTURE = TracebackCapture()
api_hooks.send_telegram_error = CAPTURE


def describe(traceback_text):
  """(tipo, messaggio, file:riga dell'ultimo frame dentro src/)"""
  frames = re.findall(r'File "[^"]*?/src/([^"]+)", line (\d+)', traceback_text)
  where = f'{frames[-1][0]}:{frames[-1][1]}' if frames else '?'
  last = traceback_text.strip().splitlines()[-1]
  kind, _, message = last.partition(': ')
  return kind.split('.')[-1], message[:70], where


def users_by_role():
  with database_api.engine.connect() as connection:
    rows = connection.execute(
      text('select id, role::text as role, company_id from "user" where company_id is not null order by id')
    ).fetchall()
  found = {}
  for row in rows:
    found.setdefault((row.role, row.company_id), row)
  return found


def token(row):
  return create_jwt_token(SimpleNamespace(id=row.id, role=UserRole[row.role], company_id=row.company_id))


def real_ids():
  tables = {
    'order': 'order',
    'user': 'user',
    'transport': 'transport',
    'service': 'service',
    'schedule': 'schedule',
    'collection': 'collection_point',
    'company': 'company',
  }
  ids = {}
  with database_api.engine.connect() as connection:
    for key, table in tables.items():
      ids[key] = connection.execute(text(f'select min(id) from "{table}"')).scalar()
  return ids


def fill(rule, value):
  return re.sub(r'<(?:[^:>]+:)?[^>]+>', str(value), rule.rule)


def main():
  users = users_by_role()
  roles = {f'{role}/{company}': row for (role, company), row in users.items() if role in {r.name for r in UserRole}}
  print(f'utenti di prova: {sorted(roles)}')
  ids = real_ids()
  client = app.test_client()
  rules = [r for r in app.url_map.iter_rules() if not SKIP.match(r.rule)]
  print(f'{len(rules)} rotte')

  unhandled = defaultdict(list)
  server_errors = defaultdict(set)
  anonymous_ok = defaultdict(set)
  matrix = defaultdict(Counter)

  actors = {'anonimo': None, 'token-non-valido': 'xxx.yyy.zzz'} | {name: token(row) for name, row in roles.items()}
  for rule in rules:
    methods = [m for m in rule.methods if m in ('GET', 'POST', 'PUT', 'DELETE', 'PATCH')]
    has_params = '<' in rule.rule
    values = [ids['order'] or 1, 99999999] + BAD_VALUES if has_params else [None]
    for method in methods:
      for value in values:
        # DELETE/PUT con un id reale cancellerebbero davvero i dati della copia: solo id inesistenti o malformati
        if method in ('DELETE', 'PUT', 'PATCH') and value == (ids['order'] or 1):
          continue
        url = fill(rule, value) if has_params else rule.rule
        bodies = BODIES if method in ('POST', 'PUT', 'PATCH') else [None]
        for actor, jwt_token in actors.items():
          for body in bodies:
            kwargs = {'headers': {'Authorization': jwt_token}} if jwt_token else {}
            if body is not None:
              kwargs['data'] = json.dumps(body)
              kwargs['content_type'] = 'application/json'
            CAPTURE.take()
            try:
              response = client.open(url, method=method, **kwargs)
              status = response.status_code
              for traceback_text in CAPTURE.take():
                kind, message, where = describe(traceback_text)
                if kind in IGNORED_EXCEPTIONS:
                  continue
                unhandled[(method, rule.rule, kind, where)].append((actor, str(body)[:30], status, message))
            except Exception as error:  # il test client rilancia le eccezioni non gestite
              status = 500
              server_errors[(method, rule.rule)].add(f'{actor}: {type(error).__name__}: {str(error)[:90]}')
              matrix[(method, rule.rule)][actor + ':EXC'] += 1
              continue
            matrix[(method, rule.rule)][f'{actor}:{status}'] += 1
            if status >= 500:
              server_errors[(method, rule.rule)].add(f'{actor} {url} body={str(body)[:40]} -> {status}')
            if actor == 'anonimo' and status < 400:
              anonymous_ok[(method, rule.rule)].add(status)

  print(f'\n== 5xx: {len(server_errors)} rotte ==')
  for (method, rule), errors in sorted(server_errors.items()):
    print(f'KO {method:6} {rule}')
    for error in sorted(errors)[:3]:
      print(f'      {error}')
  print(f'\n== eccezioni non gestite (loggate dall handler globale): {len(unhandled)} combinazioni ==')
  by_where = defaultdict(list)
  for (method, rule, kind, where), hits in sorted(unhandled.items()):
    by_where[(kind, where)].append((method, rule, hits[0]))
  for (kind, where), routes in sorted(by_where.items(), key=lambda item: -len(item[1])):
    method, rule, hit = routes[0]
    print(f'KO {kind:28} {where:42} rotte={len(routes):3} es. {method} {rule} [{hit[0]}, http {hit[2]}] {hit[3]}')
  statuses = Counter(hit[2] for hits in unhandled.values() for hit in hits)
  print(f'codici HTTP restituiti per quelle eccezioni: {dict(statuses)}')

  print(f'\n== raggiungibili senza token (2xx/3xx): {len(anonymous_ok)} ==')
  for (method, rule), statuses in sorted(anonymous_ok.items()):
    print(f'   {method:6} {rule} {sorted(statuses)}')

  cross_tenant(users, ids, client)


def cross_tenant(users, ids, client):
  print('\n== isolamento tra company ==')
  with database_api.engine.connect() as connection:
    companies = [r[0] for r in connection.execute(text('select id from company order by id')).fetchall()]
    if len(companies) < 2:
      print('serve almeno una seconda company')
      return
    owner, other = companies[0], companies[1]
    samples = {
      'order': connection.execute(text('select id from "order" where company_id=:c limit 1'), {'c': owner}).scalar(),
      'schedule': connection.execute(
        text('select id from schedule where company_id=:c limit 1'), {'c': owner}
      ).scalar(),
      'transport': connection.execute(
        text('select id from transport where company_id=:c limit 1'), {'c': owner}
      ).scalar(),
      'user': connection.execute(text('select id from "user" where company_id=:c limit 1'), {'c': owner}).scalar(),
      'collection_point': connection.execute(
        text('select id from collection_point where company_id=:c limit 1'), {'c': owner}
      ).scalar(),
    }
  intruders = [
    (role, row) for (role, company), row in users.items() if company == other and role in ('Admin', 'ADMIN', 'ADMIN')
  ]
  intruders = [(r, row) for (r, c), row in users.items() if c == other and r in ('ADMIN', 'OPERATOR', 'CUSTOMER')]
  probes = [
    ('GET', '/order/{order}'),
    ('GET', '/schedule/{schedule}'),
    ('GET', '/transport/{transport}'),
    ('GET', '/user/{user}'),
    ('GET', '/collection-point/{collection_point}'),
  ]
  leaks = 0
  for role, row in intruders:
    for method, template in probes:
      key = re.search(r'\{(\w+)\}', template).group(1)
      if not samples.get(key):
        continue
      url = template.format(**samples)
      response = client.open(url, method=method, headers={'Authorization': token(row)})
      body = response.get_json(silent=True)
      leaked = response.status_code == 200 and isinstance(body, dict) and body.get('status') == 'ok'
      leaks += leaked
      print(f'{"KO " if leaked else "OK "} {role} della company {other} -> {method} {url}: {response.status_code}')
  print(f'{leaks} possibili fughe tra company')


if __name__ == '__main__':
  main()

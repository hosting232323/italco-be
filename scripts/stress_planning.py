# ruff: noqa: T201
"""Stress test della pianificazione automatica su una copia della produzione.

Gira dentro il processo (Flask test client) contro un database che contenga il
dump ripristinato e migrato: i clienti, i servizi, i punti vendita e gli
indirizzi sono quelli veri. Nominatim e OSRM sono finti (coordinate
deterministiche, latenza e guasti configurabili): il test misura quante
chiamate esterne fa il codice e come regge quando falliscono, senza martellare
i server veri.

  python -m scripts.stress_planning setup
  python -m scripts.stress_planning constraints --customers 20
  python -m scripts.stress_planning create --orders 300 --check-fraction 0.3
  python -m scripts.stress_planning concurrent --orders 200 --threads 4
  python -m scripts.stress_planning lifecycle --orders 100
  python -m scripts.stress_planning create --orders 200 --fail-rate 0.2

Ogni scenario stampa le latenze, i codici HTTP, le chiamate esterne e le
violazioni di invarianti trovate sul database. Il database va copiato prima
(createdb -T) perche' gli scenari scrivono ordini e borderò.
"""

import argparse
import hashlib
import math
import os
import random
import statistics
import sys
import tempfile
import threading
import time
from collections import Counter, defaultdict
from datetime import date, timedelta
from types import SimpleNamespace

from dotenv import load_dotenv

if 'DATABASE_URL' not in os.environ:
  sys.exit('DATABASE_URL obbligatoria: punta a una copia del dump, mai alla produzione')
load_dotenv('.env.test')
os.environ.setdefault('STATIC_FOLDER', tempfile.mkdtemp(prefix='italco-stress-static-'))

import requests  # noqa: E402
from sqlalchemy import event, text  # noqa: E402

import database_api  # noqa: E402
import src.__main__  # noqa: E402,F401
from database_api import scope, Session  # noqa: E402
from database_api.operations import create  # noqa: E402
from src import app  # noqa: E402
from src.database.enum import OrderType, UserRole  # noqa: E402
from src.database.schema import Company, DeliveryCoverageCap, DeliveryCoverageEntry  # noqa: E402
from src.end_points.users.session import create_jwt_token  # noqa: E402
from src.utils import caps as caps_module  # noqa: E402

COMPANY_ID = 1
SLOTS = [('09:00', '12:00'), ('12:00', '15:00'), ('15:00', '18:00')]


# ---------------------------------------------------------------------------
# Servizi esterni finti
# ---------------------------------------------------------------------------


class FakeNet:
  """Sostituisce requests.get per Nominatim e OSRM: coordinate deterministiche."""

  def __init__(self):
    self.calls = Counter()
    self.lock = threading.Lock()
    self.latency = 0.0
    self.fail_rate = 0.0

  def reset(self):
    with self.lock:
      self.calls.clear()

  def snapshot(self):
    with self.lock:
      return Counter(self.calls)

  @staticmethod
  def _hash(text_value: str, salt: str) -> float:
    digest = hashlib.md5(f'{salt}:{text_value}'.encode()).digest()
    return int.from_bytes(digest[:4], 'big') / 2**32

  def cap_coord(self, cap: str):
    return 41.0 + self._hash(cap, 'lat') * 0.5, 16.6 + self._hash(cap, 'lon') * 0.6

  def address_coord(self, address: str):
    # il comune (penultimo pezzo dopo la virgola) fissa il centro, la via sposta di ~2 km
    parts = [p.strip().lower() for p in address.split(',') if p.strip()]
    city = parts[-2] if len(parts) >= 2 else 'bari'
    base_lat, base_lon = self.cap_coord(city)
    return base_lat + (self._hash(address, 'a') - 0.5) * 0.04, base_lon + (self._hash(address, 'b') - 0.5) * 0.04

  def _maybe_fail(self):
    if self.fail_rate and random.random() < self.fail_rate:
      raise random.choice([requests.ConnectionError('injected'), requests.Timeout('injected')])

  @staticmethod
  def _minutes(a, b):
    km = math.dist((a[0] * 111, a[1] * 84), (b[0] * 111, b[1] * 84)) * 1.3
    return km / 40 * 3600

  def get(self, url, params=None, headers=None, timeout=None):
    with self.lock:
      self.calls['osrm' if 'osrm' in url else 'nominatim'] += 1
    if self.latency:
      time.sleep(self.latency)
    self._maybe_fail()
    if 'nominatim' in url:
      params = params or {}
      if 'q' in params:
        lat, lon = self.address_coord(params['q'])
      elif 'postalcode' in params:
        lat, lon = self.cap_coord(params['postalcode'])
      else:
        return _Response([])
      return _Response([{'lat': str(lat), 'lon': str(lon), 'address': {'postcode': '70100', 'county': 'Bari'}}])

    coords = [tuple(map(float, pair.split(',')))[::-1] for pair in url.split('/driving/')[1].split('?')[0].split(';')]
    if '/table/' in url:
      return _Response({'code': 'Ok', 'durations': [[self._minutes(a, b) for b in coords] for a in coords]})
    remaining = list(range(1, len(coords)))
    cycle = [0]
    while remaining:
      nxt = min(remaining, key=lambda i: self._minutes(coords[cycle[-1]], coords[i]))
      remaining.remove(nxt)
      cycle.append(nxt)
    waypoints = [None] * len(coords)
    for position, index in enumerate(cycle):
      waypoints[index] = {'waypoint_index': position}
    legs = [
      {'duration': self._minutes(coords[cycle[k]], coords[cycle[(k + 1) % len(cycle)]])} for k in range(len(cycle))
    ]
    return _Response({'code': 'Ok', 'waypoints': waypoints, 'trips': [{'legs': legs}]})


class _Response:
  status_code = 200

  def __init__(self, payload):
    self._payload = payload

  def json(self):
    return self._payload

  def raise_for_status(self):
    return None


NET = FakeNet()
requests.get = NET.get


class QueryCounter:
  def __init__(self):
    self.count = 0
    self.lock = threading.Lock()
    event.listen(database_api.engine, 'before_cursor_execute', self._hit)

  def _hit(self, *_):
    with self.lock:
      self.count += 1


QUERIES = QueryCounter()


# ---------------------------------------------------------------------------
# Setup: copertura, durate, veicoli
# ---------------------------------------------------------------------------


def setup(args):
  with database_api.engine.begin() as connection:
    rows = connection.execute(
      text('select cap, count(*) c from "order" where company_id = :c group by 1 order by 2 desc'), {'c': COMPANY_ID}
    ).fetchall()
    total = sum(r.c for r in rows)
    caps, running = [], 0
    for row in rows:
      caps.append(row.cap)
      running += row.c
      if running / total >= args.coverage:
        break
    connection.execute(text('delete from delivery_coverage_cap'))
    connection.execute(text('delete from delivery_coverage_entry'))
    connection.execute(text('update service set duration = 20 + (id % 4) * 10 where duration is null'))
    connection.execute(
      text(
        "update company set automatic_planning = true, activity_start_time = '08:00', activity_end_time = '19:00' where id = :c"
      ),
      {'c': COMPANY_ID},
    )
    vehicles = [
      r.id
      for r in connection.execute(text('select id from transport where company_id = :c order by id'), {'c': COMPANY_ID})
    ]

  vehicles = vehicles[: args.vehicles]
  zones = defaultdict(list)
  for index, cap in enumerate(caps):
    zones[index % max(1, len(vehicles) // 2)].append(cap)

  with scope(company_id=COMPANY_ID):
    for zone_index, zone_caps in zones.items():
      for vehicle in vehicles[zone_index * 2 : zone_index * 2 + 2] or vehicles[-1:]:
        for day in range(6):
          for start, end in SLOTS:
            entry = create(
              DeliveryCoverageEntry,
              {'day_of_week': day, 'transport_id': vehicle, 'start_time': start, 'end_time': end, 'polygon': None},
            )
            for cap in zone_caps:
              create(DeliveryCoverageCap, {'entry_id': entry.id, 'cap': cap})
    if args.polygon and vehicles:
      for day in range(6):
        create(
          DeliveryCoverageEntry,
          {
            'day_of_week': day,
            'transport_id': vehicles[-1],
            'start_time': '12:00',
            'end_time': '15:00',
            'polygon': [[41.0, 16.6], [41.5, 16.6], [41.5, 17.2], [41.0, 17.2]],
          },
        )
  print(f'copertura: {len(caps)} CAP ({args.coverage:.0%} del volume), {len(vehicles)} veicoli, {len(zones)} zone')


# ---------------------------------------------------------------------------
# Dati di prova
# ---------------------------------------------------------------------------


def load_templates(limit_customers=None):
  with database_api.engine.connect() as connection:
    orders = connection.execute(
      text(
        """
        select o.id, o.address, o.cap, o.type::text as type, o.dpc - o.created_at::date as dpc_offset,
               su.user_id, p.name, su.service_id, p.collection_point_id
        from "order" o join product p on p.order_id = o.id join service_user su on su.id = p.service_user_id
        join "user" u on u.id = su.user_id
        where o.company_id = :c and o.type = 'DELIVERY' and u.role = 'CUSTOMER' and u.automatic_planning
          and o.operator_note is null
        """
      ),
      {'c': COMPANY_ID},
    ).fetchall()
  by_order = defaultdict(list)
  for row in orders:
    by_order[row.id].append(row)
  templates = []
  for rows in by_order.values():
    products = {}
    for row in rows:
      data = products.setdefault(row.name, {'services': [], 'collection_point': None})
      data['services'].append({'id': row.service_id})
      if row.collection_point_id:
        data['collection_point'] = {'id': row.collection_point_id}
    products = {name: {k: v for k, v in data.items() if v is not None} for name, data in products.items()}
    templates.append(
      SimpleNamespace(
        user_id=rows[0].user_id,
        address=rows[0].address,
        cap=rows[0].cap,
        dpc_offset=max(rows[0].dpc_offset or 0, 0),
        products=products,
      )
    )
  if limit_customers:
    keep = {t.user_id for t in templates[:0]} or set(sorted({t.user_id for t in templates})[:limit_customers])
    templates = [t for t in templates if t.user_id in keep]
  return templates


def token_for(user_id):
  return create_jwt_token(SimpleNamespace(id=user_id, role=UserRole.CUSTOMER, company_id=COMPANY_ID))


def pick_date(offset):
  day = date.today() + timedelta(days=max(1, offset))
  while day.weekday() == 6:
    day += timedelta(days=1)
  return day


def order_payload(template, day, slot=None):
  payload = {
    'type': OrderType.DELIVERY.value,
    'addressee': 'Test Stress',
    'address': template.address,
    'cap': template.cap,
    'dpc': day.isoformat(),
    'drc': date.today().isoformat(),
    'products': template.products,
  }
  if slot:
    payload['delivery_slot_start'], payload['delivery_slot_end'] = slot
  return payload


def check_payload(template):
  return {
    'cap': template.cap,
    'address': template.address,
    'products': template.products,
    'services_id': [s['id'] for p in template.products.values() for s in p['services']],
  }


# ---------------------------------------------------------------------------
# Misure
# ---------------------------------------------------------------------------


class Report:
  def __init__(self):
    self.latency = defaultdict(list)
    self.status = defaultdict(Counter)
    self.errors = Counter()
    self.lock = threading.Lock()

  def record(self, name, seconds, status, error=None):
    with self.lock:
      self.latency[name].append(seconds)
      self.status[name][status] += 1
      if error:
        self.errors[error[:160]] += 1

  def print(self):
    for name, values in self.latency.items():
      values = sorted(values)
      p95 = values[min(len(values) - 1, int(len(values) * 0.95))]
      print(
        f'{name:18} n={len(values):5} p50={statistics.median(values) * 1000:8.0f}ms p95={p95 * 1000:8.0f}ms '
        f'max={values[-1] * 1000:8.0f}ms  http={dict(self.status[name])}'
      )
    for message, count in self.errors.most_common(8):
      print(f'  errore x{count}: {message}')


def call(client, report, name, method, url, token, payload):
  started = time.perf_counter()
  error = None
  try:
    response = getattr(client, method)(url, json=payload, headers={'Authorization': token})
    status = response.status_code
    body = response.get_json(silent=True) or {}
    if status >= 500:
      error = response.get_data(as_text=True)[:200]
    elif body.get('status') == 'ko':
      error = f'ko: {body.get("message")}'
  except Exception as exception:  # il client di test rilancia le eccezioni non gestite
    status, body, error = 'EXC', {}, f'{type(exception).__name__}: {exception}'
  report.record(name, time.perf_counter() - started, status, error)
  return status, body


def show_external(before, label):
  after = NET.snapshot()
  print(f'{label}: nominatim={after["nominatim"] - before["nominatim"]} osrm={after["osrm"] - before["osrm"]}')


# ---------------------------------------------------------------------------
# Scenari
# ---------------------------------------------------------------------------


def scenario_constraints(args):
  templates = load_templates(args.customers)
  report = Report()
  client = app.test_client()
  for template in random.sample(templates, min(args.samples, len(templates))):
    NET.reset()
    queries = QUERIES.count
    status, body = call(
      client,
      report,
      'check-constraints',
      'post',
      '/check-constraints',
      token_for(template.user_id),
      check_payload(template),
    )
    print(
      f'  cap={template.cap} prodotti={len(template.products)} http={status} giorni={len(body.get("dates", []))} '
      f'query={QUERIES.count - queries} esterne={dict(NET.snapshot())}'
    )
  report.print()


def do_create(client, report, template, check_fraction):
  token = token_for(template.user_id)
  day = pick_date(template.dpc_offset)
  slot = None
  if random.random() < check_fraction:
    status, body = call(
      client, report, 'check-constraints', 'post', '/check-constraints', token, check_payload(template)
    )
    slots = (body.get('slots') or {}).get(day.isoformat()) if status == 200 else None
    if slots:
      choice = random.choice(slots)
      slot = (choice['start'], choice['end'])
  return call(client, report, 'create-order', 'post', '/order', token, order_payload(template, day, slot))


def scenario_create(args):
  templates = load_templates()
  report = Report()
  client = app.test_client()
  created = []
  started = time.perf_counter()
  for index in range(args.orders):
    template = random.choice(templates)
    before_queries, before_calls, before_time = QUERIES.count, NET.snapshot(), time.perf_counter()
    status, body = do_create(client, report, template, args.check_fraction)
    if status == 200 and body.get('order'):
      created.append(body['order']['id'])
    after = NET.snapshot()
    print(
      f'  #{index + 1:4} {time.perf_counter() - before_time:7.2f}s query={QUERIES.count - before_queries:6} '
      f'nominatim={after["nominatim"] - before_calls["nominatim"]:3} osrm={after["osrm"] - before_calls["osrm"]:4} http={status}',
      flush=True,
    )
  report.print()
  print(f'totale {time.perf_counter() - started:.0f}s, query DB {QUERIES.count}, esterne {dict(NET.snapshot())}')
  check_invariants(created)


def scenario_concurrent(args):
  templates = load_templates()
  report = Report()
  created, lock = [], threading.Lock()
  # tutti sulla stessa data e sugli stessi CAP: il caso peggiore per le gare
  hot = random.sample(templates, min(len(templates), 40))
  jobs = [random.choice(hot) for _ in range(args.orders)]
  days = [pick_date(random.randint(1, 12)) for _ in jobs] if not args.hot else [pick_date(2)] * len(jobs)
  jobs = list(zip(jobs, days))

  def worker(chunk):
    client = app.test_client()
    for template, day in chunk:
      status, body = call(
        client, report, 'create-order', 'post', '/order', token_for(template.user_id), order_payload(template, day)
      )
      if status == 200 and body.get('order'):
        with lock:
          created.append(body['order']['id'])

  threads = [threading.Thread(target=worker, args=(jobs[i :: args.threads],)) for i in range(args.threads)]
  started = time.perf_counter()
  for thread in threads:
    thread.start()
  for thread in threads:
    thread.join()
  report.print()
  print(f'totale {time.perf_counter() - started:.0f}s, esterne {dict(NET.snapshot())}')
  check_invariants(created)


def scenario_fill(args):
  """Riempie una sola fascia servita da due veicoli e mostra dove finisce ogni ordine.

  La regola dichiarata e' "si riempie prima il veicolo con id piu' basso, poi il
  successivo": il primo veicolo deve arrivare a saturazione prima che il secondo
  riceva il primo ordine.
  """
  templates = load_templates()
  with database_api.engine.connect() as connection:
    zone = connection.execute(
      text(
        """select array_agg(distinct c.cap) caps, e.transport_id from delivery_coverage_entry e
           join delivery_coverage_cap c on c.entry_id = e.id where e.day_of_week = 0 and e.start_time = '09:00' group by e.transport_id order by 2"""
      )
    ).fetchall()
  by_caps = defaultdict(list)
  for row in zone:
    by_caps[tuple(row.caps)].append(row.transport_id)
  caps, vehicles = next((c, v) for c, v in by_caps.items() if len(v) >= 2)
  candidates = [t for t in templates if t.cap in caps]
  print(f'veicoli sulla stessa zona: {vehicles}, CAP {len(caps)}')
  report = Report()
  client = app.test_client()
  day = date.today() + timedelta(days=1)
  while day.weekday() != 0:
    day += timedelta(days=1)
  placed = []
  for index in range(args.orders):
    template = random.choice(candidates)
    started = time.perf_counter()
    status, body = call(
      client,
      report,
      'create-order',
      'post',
      '/order',
      token_for(template.user_id),
      order_payload(template, day, ('09:00', '12:00')),
    )
    if status == 200 and body.get('order'):
      with database_api.engine.connect() as connection:
        vehicle = connection.execute(
          text(
            'select s.transport_id from schedule_item_order sio join schedule_item si on si.id = sio.schedule_item_id '
            'join schedule s on s.id = si.schedule_id where sio.order_id = :o'
          ),
          {'o': body['order']['id']},
        ).scalar()
      placed.append(vehicle)
      print(f'  #{index + 1:3} {time.perf_counter() - started:6.2f}s -> veicolo {vehicle}', flush=True)
  print('sequenza veicoli:', placed)
  report.print()
  check_invariants([])


def scenario_spill(args):
  """Un veicolo con due fasce adiacenti a CAP diversi: la prima si satura e l'ordine trabocca sulla seconda."""
  templates = load_templates()
  with database_api.engine.connect() as connection:
    vehicle = connection.execute(
      text('select max(id) from transport where company_id = :c'), {'c': COMPANY_ID}
    ).scalar()
  with scope(company_id=COMPANY_ID):
    for (start, end), cap in ((('09:00', '10:00'), '70999'), (('10:00', '11:00'), '70998')):
      entry = create(
        DeliveryCoverageEntry, {'day_of_week': 2, 'transport_id': vehicle, 'start_time': start, 'end_time': end}
      )
      create(DeliveryCoverageCap, {'entry_id': entry.id, 'cap': cap})
  day = date.today() + timedelta(days=1)
  while day.weekday() != 2:
    day += timedelta(days=1)
  client = app.test_client()
  report = Report()
  for index in range(args.orders):
    template = random.choice(templates)
    template = SimpleNamespace(**{**vars(template), 'cap': '70999'})
    status, body = call(
      client,
      report,
      'create-order',
      'post',
      '/order',
      token_for(template.user_id),
      order_payload(template, day, ('09:00', '10:00')),
    )
    order = body.get('order') or {}
    with database_api.engine.connect() as connection:
      planned = connection.execute(
        text('select count(*) from schedule_item_order where order_id = :o'), {'o': order.get('id')}
      ).scalar()
    print(
      f'  #{index + 1:2} http={status} fascia={order.get("delivery_slot_start")}-{order.get("delivery_slot_end")} nel borderò={bool(planned)}',
      flush=True,
    )
  report.print()


def scenario_lifecycle(args):
  """Crea ordini pianificati poi li modifica come farebbe il cliente."""
  templates = load_templates()
  report = Report()
  client = app.test_client()
  created = []
  for _ in range(args.orders):
    template = random.choice(templates)
    status, body = do_create(client, report, template, 0)
    if status == 200 and body.get('order'):
      created.append((template, body['order']))
  moved = 0
  for template, order in random.sample(created, min(len(created), args.orders // 3)):
    new_day = pick_date(template.dpc_offset + 3)
    status, _ = call(
      client,
      report,
      'update-dpc',
      'put',
      f'/order/{order["id"]}',
      token_for(template.user_id),
      {'dpc': new_day.isoformat()},
    )
    moved += status == 200
  report.print()
  print(f'ordini spostati di data dal cliente: {moved}')
  check_invariants([o['id'] for _, o in created], check_dates=True)


# ---------------------------------------------------------------------------
# Invarianti sul database
# ---------------------------------------------------------------------------

INVARIANTS = {
  'ordini con fascia ma senza tappa nel borderò': """
    select o.id from "order" o left join schedule_item_order sio on sio.order_id = o.id
    where o.id = any(:ids) and o.delivery_slot_start is not null and sio.id is null""",
  "ordini in piu' tappe": """
    select order_id from schedule_item_order where order_id = any(:ids) group by 1 having count(*) > 1""",
  'borderò duplicati (stessa data e veicolo)': """
    select date, transport_id from schedule where transport_id is not null and date >= current_date group by 1, 2 having count(*) > 1""",
  'indici tappa duplicati nello stesso borderò': """
    select si.schedule_id, si.index from schedule_item si join schedule s on s.id = si.schedule_id where s.date >= current_date group by 1, 2 having count(*) > 1""",
  'buchi negli indici (max+1 != count)': """
    select si.schedule_id from schedule_item si join schedule s on s.id = si.schedule_id where s.date >= current_date group by 1 having max(si.index) + 1 <> count(*)""",
  "tappa d'ordine su borderò di data diversa dalla dpc": """
    select o.id from schedule_item_order sio join "order" o on o.id = sio.order_id
    join schedule_item si on si.id = sio.schedule_item_id join schedule s on s.id = si.schedule_id
    where o.id = any(:ids) and s.date <> o.dpc""",
  "tappe senza ordine ne' punto di ritiro": """
    select si.id from schedule_item si join schedule s on s.id = si.schedule_id and s.date >= current_date
    left join schedule_item_order sio on sio.schedule_item_id = si.id
    left join schedule_item_collection_point scp on scp.schedule_item_id = si.id
    where sio.id is null and scp.id is null""",
  'ordini con fascia diversa dalla tappa': """
    select o.id from schedule_item_order sio join "order" o on o.id = sio.order_id
    join schedule_item si on si.id = sio.schedule_item_id
    where o.id = any(:ids) and (si.start_time_slot <> o.delivery_slot_start or si.end_time_slot <> o.delivery_slot_end)""",
}


def check_invariants(order_ids, check_dates=False):
  print('\n== invarianti ==')
  ids = list(order_ids)
  with database_api.engine.connect() as connection:
    for label, sql in INVARIANTS.items():
      rows = connection.execute(text(sql), {'ids': ids}).fetchall()
      print(
        f'{"OK " if not rows else "KO "} {label}: {len(rows)}{"  es. " + str([tuple(r) for r in rows[:3]]) if rows else ""}'
      )
    overbooked = connection.execute(
      text(
        """
        select s.date, s.transport_id, si.start_time_slot, count(*) filter (where sio.id is not null) n,
               coalesce(sum(sv.duration), 0) minutes,
               extract(epoch from (si.end_time_slot - si.start_time_slot)) / 60 capacity
        from schedule s join schedule_item si on si.schedule_id = s.id
        left join schedule_item_order sio on sio.schedule_item_id = si.id
        left join product p on p.order_id = sio.order_id
        left join service_user su on su.id = p.service_user_id left join service sv on sv.id = su.service_id
        where si.operation_type = 'ORDER' and s.date >= current_date
        group by 1, 2, 3, si.end_time_slot having coalesce(sum(sv.duration), 0) > extract(epoch from (si.end_time_slot - si.start_time_slot)) / 60
        order by 1, 2, 3
        """
      )
    ).fetchall()
    print(f'{"OK " if not overbooked else "KO "} fasce sopra capienza (solo minuti di servizio): {len(overbooked)}')
    for row in overbooked[:5]:
      print(
        f'    {row.date} veicolo {row.transport_id} {row.start_time_slot}: {row.n} ordini, {row.minutes:.0f} min su {row.capacity:.0f}'
      )
    per_vehicle = connection.execute(
      text(
        """
        select s.transport_id, count(*) from schedule_item_order sio join schedule_item si on si.id = sio.schedule_item_id
        join schedule s on s.id = si.schedule_id where sio.order_id = any(:ids) group by 1 order by 1"""
      ),
      {'ids': ids},
    ).fetchall()
    print('ordini per veicolo:', {r.transport_id: r.count for r in per_vehicle})
    stops = connection.execute(
      text(
        'select count(*) n from schedule_item si join schedule s on s.id = si.schedule_id group by s.id order by 1 desc limit 1'
      )
    ).scalar()
    print("borderò piu' grande (tappe):", stops)


def main():
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument(
    'scenario', choices=['setup', 'constraints', 'create', 'concurrent', 'lifecycle', 'fill', 'spill']
  )
  parser.add_argument('--orders', type=int, default=200)
  parser.add_argument('--customers', type=int, default=None)
  parser.add_argument('--samples', type=int, default=10)
  parser.add_argument('--threads', type=int, default=4)
  parser.add_argument(
    '--check-fraction', type=float, default=0.0, help='quota di ordini preceduti da /check-constraints'
  )
  parser.add_argument('--latency', type=float, default=0.02, help='secondi di latenza per chiamata esterna finta')
  parser.add_argument('--fail-rate', type=float, default=0.0, help="probabilita' di guasto di ogni chiamata esterna")
  parser.add_argument('--seed', type=int, default=1)
  parser.add_argument('--coverage', type=float, default=0.95)
  parser.add_argument('--vehicles', type=int, default=6)
  parser.add_argument('--polygon', action='store_true')
  parser.add_argument('--hot', action='store_true', help='concurrent: tutti sulla stessa data')
  args = parser.parse_args()

  random.seed(args.seed)
  NET.latency, NET.fail_rate = args.latency, args.fail_rate
  caps_module.get_lat_lon_by_address.cache_clear()
  caps_module.get_lat_lon_by_cap.cache_clear()
  globals()[f'scenario_{args.scenario}' if args.scenario != 'setup' else 'setup'](args)


if __name__ == '__main__':
  main()

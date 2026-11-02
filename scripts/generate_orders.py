"""Genera N ordini verosimili campionando lo storico del database su cui gira.

Ogni ordine sintetico e' un bootstrap di un ordine reale: cliente, tipo,
prodotti (servizio + punto vendita), piano, ascensore, note, scarto
drc/dpc rispetto alla creazione e indirizzo (con il civico rimescolato) escono
dalla distribuzione vera, quindi la distribuzione congiunta e' quella di
produzione senza doverla modellare a mano. Nomi e telefoni sono inventati.

Pensato per girare su una copia della produzione (dump ripristinato e migrato):
i clienti, i servizi e i punti vendita devono esistere, e li prende da li'.

  python -m scripts.generate_orders --count 5000 --days 5 --seed 1
  python -m scripts.generate_orders --profile                # solo statistiche
  python -m scripts.generate_orders --purge                  # toglie gli ordini generati

Gli ordini generati si riconoscono da operator_note = 'GENERATED:<run>'.
"""

# ruff: noqa: T201
import argparse
import os
import random
import re
import sys
import uuid
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse

from sqlalchemy import create_engine, insert, text

from src.database.enum import OrderStatus
from src.database.schema import History, Order, Product

MARKER = 'GENERATED:'
OPEN_STATUSES = ('ACQUIRED', 'BOOKING', 'BOOKED')
LOCAL_HOSTS = ('localhost', '127.0.0.1', '::1', 'host.docker.internal')

FIRST_NAMES = ['Mario', 'Luca', 'Giuseppe', 'Anna', 'Francesca', 'Marco', 'Giovanni', 'Maria', 'Paola', 'Vito', 'Rosa']
LAST_NAMES = ['Rossi', 'Russo', 'Ferrari', 'Esposito', 'Bianchi', 'Romano', 'Colombo', 'Ricci', 'Marino', 'Greco']
NOTES = [
  'Citofonare al secondo suonatore',
  "Chiamare mezz'ora prima",
  'Portone su strada laterale',
  'Lasciare al vicino se assente',
  "Ritiro dell'usato incluso",
  "Scale strette, misurare l'ingresso",
  'Parcheggio difficile, non ci sono posti',
]

SAMPLE_ORDERS = text(
  """
  select id, company_id, type, status, address, cap, floor, elevator, confirmed, anomaly,
         external_id is not null as has_external, external_status,
         nullif(customer_note, '') is not null as has_note,
         nullif(addressee_contact, '') is not null as has_contact,
         (drc - created_at::date) as drc_offset, (dpc - created_at::date) as dpc_offset,
         extract(dow from created_at) as created_dow
  from "order"
  where operator_note is null or operator_note not like :marker
  """
)
SAMPLE_PRODUCTS = text(
  """
  select p.order_id, p.name, p.service_user_id, p.collection_point_id
  from product p join "order" o on o.id = p.order_id
  where o.operator_note is null or o.operator_note not like :marker
  """
)


def load_templates(connection, company_id=None):
  marker = {'marker': MARKER + '%'}
  products = {}
  for row in connection.execute(SAMPLE_PRODUCTS, marker):
    products.setdefault(row.order_id, []).append(row)

  templates = []
  for row in connection.execute(SAMPLE_ORDERS, marker):
    if company_id and row.company_id != company_id:
      continue
    if row.id in products:
      templates.append((row, products[row.id]))
  return templates


def print_profile(templates):
  print(f'ordini campionabili: {len(templates)}')
  print('per company:', dict(Counter(order.company_id for order, _ in templates)))
  print('per tipo:', dict(Counter(order.type for order, _ in templates)))
  print('per status:', dict(Counter(order.status for order, _ in templates)))
  sizes = Counter(len(products) for _, products in templates)
  print('prodotti per ordine:', {size: sizes[size] for size in sorted(sizes)[:8]})
  print('CAP distinti:', len({order.cap for order, _ in templates}))


def randomize_civic(address: str) -> str:
  return re.sub(r'\b\d+\b', lambda _: str(random.randint(1, 180)), address, count=1)


def build_rows(templates, count, days, status_mode, run_id):
  # Il peso di ogni giorno d'intake e' quello vero del giorno della settimana
  # (postgres: 0 = domenica), cosi' i weekend restano leggeri come in produzione.
  weight_by_dow = Counter(int(order.created_dow) for order, _ in templates)
  calendar = [date.today() + timedelta(days=k) for k in range(days)]
  day_weights = [weight_by_dow[(day.weekday() + 1) % 7] or 1 for day in calendar]
  status_pool = [order.status for order, _ in templates if order.status in OPEN_STATUSES] or ['ACQUIRED']

  orders = []
  for index in range(count):
    order, products = random.choice(templates)
    intake = random.choices(calendar, day_weights)[0]
    status = OrderStatus[random.choice(status_pool) if status_mode == 'open' else order.status]

    orders.append(
      {
        'company_id': order.company_id,
        'status': status,
        'type': order.type,
        'addressee': f'{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}',
        'address': randomize_civic(order.address),
        'cap': order.cap,
        'addressee_contact': f'3{random.randint(100000000, 999999999)}' if order.has_contact else None,
        'customer_note': random.choice(NOTES) if order.has_note else None,
        'operator_note': f'{MARKER}{run_id}',
        # Gli scarti negativi dello storico sono import e backfill: la dpc di un
        # ordine nuovo non cade prima dell'intake, la drc non lo supera.
        'dpc': intake + timedelta(days=max(order.dpc_offset or 0, 0)),
        'drc': intake + timedelta(days=min(order.drc_offset or 0, 0)),
        'booking_date': intake if status == OrderStatus.BOOKED else None,
        'floor': order.floor,
        'elevator': order.elevator,
        'confirmed': order.confirmed,
        'anomaly': order.anomaly,
        'external_id': f'GEN-{run_id}-{index}' if order.has_external else None,
        'external_status': order.external_status,
        '_products': products,
      }
    )
  return orders


def insert_orders(connection, orders, batch_size=2000):
  """Inserisce ordini, prodotti e cronologia a lotti; ritorna gli id creati."""
  created = []
  for start in range(0, len(orders), batch_size):
    batch = orders[start : start + batch_size]
    payload = [{key: value for key, value in order.items() if key != '_products'} for order in batch]
    ids = [row.id for row in connection.execute(insert(Order).returning(Order.id), payload)]

    products, history = [], []
    for order_id, order in zip(ids, batch):
      for product in order['_products']:
        products.append(
          {
            'order_id': order_id,
            'company_id': order['company_id'],
            'name': product.name,
            'service_user_id': product.service_user_id,
            'collection_point_id': product.collection_point_id,
          }
        )
      # Come track_order_history: una riga per lo status iniziale, una se nasce confermato.
      history.append(
        {
          'order_id': order_id,
          'company_id': order['company_id'],
          'status': {'type': 'status', 'value': order['status'].value},
        }
      )
      if order['confirmed']:
        history.append(
          {'order_id': order_id, 'company_id': order['company_id'], 'status': {'type': 'confirmed', 'value': True}}
        )

    connection.execute(insert(Product), products)
    connection.execute(insert(History), history)
    created.extend(ids)
    print(f'  {len(created)}/{len(orders)}')
  return created


def purge(connection):
  marker = {'marker': MARKER + '%'}
  generated = 'select id from "order" where operator_note like :marker'
  for table in ('schedule_item_order', 'history', 'product', 'photo'):
    connection.execute(text(f'delete from {table} where order_id in ({generated})'), marker)
  removed = connection.execute(text('delete from "order" where operator_note like :marker'), marker).rowcount
  print(f'rimossi {removed} ordini generati')


def main(argv=None):
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument('--count', type=int, default=1000, help='numero di ordini da generare')
  parser.add_argument('--days', type=int, default=1, help='giorni di intake su cui spalmare gli ordini, da oggi')
  parser.add_argument('--company-id', type=int, help='campiona solo gli ordini di questa company')
  parser.add_argument(
    '--status', choices=['open', 'real'], default='open', help='open: ACQUIRED/BOOKING/BOOKED; real: come lo storico'
  )
  parser.add_argument('--seed', type=int, help='seme per rendere la generazione riproducibile')
  parser.add_argument('--profile', action='store_true', help='stampa le statistiche dello storico e non scrive nulla')
  parser.add_argument('--purge', action='store_true', help='rimuove tutti gli ordini generati')
  parser.add_argument('--allow-remote', action='store_true', help='consente di girare su un host non locale')
  args = parser.parse_args(argv)

  url = os.environ['DATABASE_URL']
  host = urlparse(url).hostname
  if host not in LOCAL_HOSTS and not args.allow_remote:
    sys.exit(f"{host} non e' locale: non scrivo ordini finti li'. Usa --allow-remote solo se sai cosa fai.")

  if args.seed is not None:
    random.seed(args.seed)

  with create_engine(url).begin() as connection:
    if args.purge:
      return purge(connection)

    templates = load_templates(connection, args.company_id)
    if not templates:
      sys.exit('nessun ordine storico da cui campionare')
    print_profile(templates)
    if args.profile:
      return

    run_id = f'{datetime.now(timezone.utc):%y%m%d%H%M}-{uuid.uuid4().hex[:4]}'
    created = insert_orders(connection, build_rows(templates, args.count, args.days, args.status, run_id))
    print(f'creati {len(created)} ordini, run {run_id}')


if __name__ == '__main__':
  main()

"""Reviewable, stale-safe repair of existing order/service type mismatches.

Run as python -m scripts.repair_order_service_types --help. Never repairs at import.
"""

import argparse
import hashlib
import json
import os
from datetime import date, datetime
from enum import Enum
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from src.database.schema import (
  Order,
  Product,
  Service,
  ServiceUser,
  ScheduleItemOrder,
  RaeProduct,
  ScheduleItem,
  Schedule,
)
from src.order_integrity import (
  InvalidOrderProductsError,
  lock_order_service_integrity,
  order_service_rows,
  partition_order,
  split_order_by_service_type,
)


FORMAT_VERSION = 2


def json_default(value):
  if isinstance(value, Enum):
    return value.name
  if isinstance(value, (date, datetime)):
    return value.isoformat()
  if isinstance(value, bytes):
    return {'sha256': hashlib.sha256(value).hexdigest()}
  return str(value)


def digest(value):
  return hashlib.sha256(json.dumps(value, default=json_default, sort_keys=True).encode('utf-8')).hexdigest()


def record(entity):
  return {column.name: getattr(entity, column.name) for column in entity.__table__.columns}


def build_plan(session, company_id=None, order_ids=None):
  query = (
    session.query(Order)
    .join(Product, Product.order_id == Order.id)
    .join(ServiceUser, ServiceUser.id == Product.service_user_id)
    .join(Service, Service.id == ServiceUser.service_id)
    .filter(Order.type != Service.type)
  )
  if company_id is not None:
    query = query.filter(Order.company_id == company_id)
  if order_ids is not None:
    query = query.filter(Order.id.in_(order_ids))
  entries = []
  for order in query.order_by(Order.company_id, Order.id).all():
    rows = order_service_rows(order.id, session)
    links = (
      session.query(ScheduleItemOrder)
      .filter(ScheduleItemOrder.order_id == order.id)
      .order_by(ScheduleItemOrder.id)
      .all()
    )
    schedule_ids = [link.schedule_item_id for link in links]
    linked_items = session.query(ScheduleItem).filter(ScheduleItem.id.in_(schedule_ids)).all()
    linked_schedule_ids = {item.schedule_id for item in linked_items}
    items = (
      session.query(ScheduleItem)
      .filter(ScheduleItem.schedule_id.in_(linked_schedule_ids))
      .order_by(ScheduleItem.id)
      .all()
    )
    schedules = session.query(Schedule).filter(Schedule.id.in_(linked_schedule_ids)).order_by(Schedule.id).all()
    rae_ids = sorted({product.rae_product_id for product, _, _ in rows if product.rae_product_id})
    raes = session.query(RaeProduct).filter(RaeProduct.id.in_(rae_ids)).order_by(RaeProduct.id).all()
    rae_refs = session.query(Product).filter(Product.rae_product_id.in_(rae_ids)).order_by(Product.id).all()
    snapshot = {
      'order': record(order),
      'products_and_services': [[record(entity) for entity in row] for row in rows],
      'schedule_links': [record(link) for link in links],
      'schedule_items': [record(item) for item in items],
      'schedules': [record(schedule) for schedule in schedules],
      'rae': [record(rae) for rae in raes],
      'rae_references': [record(product) for product in rae_refs],
    }
    entry = {
      'order_id': order.id,
      'company_id': order.company_id,
      'order_type': order.type.name,
      'status': order.status.name,
      'created_at': json_default(order.created_at),
      'updated_at': json_default(order.updated_at),
      'version': order.version,
      'snapshot_sha256': digest(snapshot),
      'schedule_item_ids': schedule_ids,
      'schedule_action': 'Tappe distinte adiacenti; indici successivi incrementati per ogni nuovo ordine',
      'rae_ids': rae_ids,
      'mark_retained_on_original': order.mark,
      'partitions': {},
      'blocker': None,
    }
    try:
      groups, original_type, _ = partition_order(order, session)
      entry['original_type_after'] = original_type.name
      entry['partitions'] = {kind.name: [product.id for product in products] for kind, products in groups.items()}
      entry['new_orders'] = len(groups) - 1
    except InvalidOrderProductsError as error:
      entry['blocker'] = str(error)
    entries.append(entry)
  return {
    'format_version': FORMAT_VERSION,
    'database': session.execute(text('SELECT current_database()')).scalar_one(),
    'company_id': company_id,
    'entries': entries,
  }


def apply_plan(session, plan):
  if plan.get('format_version') != FORMAT_VERSION:
    raise ValueError('Formato piano non supportato.')
  if any(entry['blocker'] for entry in plan['entries']):
    raise ValueError('Il piano contiene casi bloccati: risolverli o generare un piano con --order-id espliciti.')
  # Acquire before table locks, matching structural application writers. Other
  # writers (status/RAEE/schedules/SQL) are held off while the snapshot is checked.
  session.execute(text("SET LOCAL lock_timeout = '5s'"))
  lock_order_service_integrity(session)
  session.execute(
    text(
      'LOCK TABLE "order", product, service, service_user, schedule_item_order, schedule_item, schedule, rae_product '
      'IN SHARE ROW EXCLUSIVE MODE'
    )
  )
  current = build_plan(session, plan['company_id'], [entry['order_id'] for entry in plan['entries']])
  if digest(current) != digest(plan):
    raise ValueError(
      'Piano obsoleto o database differente: rigenerare e riesaminare il dry-run. Nessuna modifica applicata.'
    )
  results = []
  for entry in plan['entries']:
    order = session.get(Order, entry['order_id'])
    targets = split_order_by_service_type(order, session)
    results.append({'original_order_id': order.id, 'orders': {target.type.name: target.id for target in targets}})
  session.flush()
  return results


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--company-id', type=int)
  parser.add_argument(
    '--order-id', type=int, action='append', help='Ripetibile; omesso include tutti gli ordini incoerenti'
  )
  parser.add_argument('--output', type=Path, required=True, help='Nuovo file JSON del piano o del risultato')
  parser.add_argument('--apply', type=Path, metavar='PIANO_JSON', help='Applica esattamente un piano gia esaminato')
  args = parser.parse_args()
  if args.apply and (args.company_id is not None or args.order_id is not None):
    parser.error('Con --apply la selezione proviene solo dal piano.')
  # Open exclusively before writing the DB, so an existing or unwritable output
  # cannot turn a successful commit into an unrecorded operation.
  with args.output.open('x', encoding='utf-8') as output:
    engine = create_engine(os.environ['DATABASE_URL'])
    try:
      with Session(engine, expire_on_commit=False) as session:
        if session.execute(text('SELECT version_num FROM alembic_version')).scalar_one() != '057':
          raise ValueError('Eseguire con schema alla revisione 057; la bonifica non applica migrazioni.')
        session.rollback()
        if args.apply:
          plan = json.loads(args.apply.read_text(encoding='utf-8'))
          result = {'applied': apply_plan(session, plan)}
          session.commit()
        else:
          session.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
          result = build_plan(session, args.company_id, args.order_id)
          session.rollback()
        json.dump(result, output, default=json_default, indent=2, ensure_ascii=False)
        output.write('\n')
    finally:
      engine.dispose()


if __name__ == '__main__':
  main()

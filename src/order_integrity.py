"""Order/service type invariant and transactional partitioning of imported orders."""

from collections import defaultdict
from sqlalchemy import text
from database_api.operations import create
from .database.schema import Order, Product, Service, ServiceUser, RaeProduct, ScheduleItemOrder, ScheduleItem


class InvalidOrderProductsError(ValueError):
  pass


def lock_order_service_integrity(session):
  # Shared by catalogue edits and structural order writes. Transaction-scoped:
  # a service cannot change type between validating it and committing an import.
  session.execute(text('SELECT pg_advisory_xact_lock(736214, 1)'))


def order_service_rows(order_id, session):
  return (
    session.query(Product, ServiceUser, Service)
    .join(ServiceUser, Product.service_user_id == ServiceUser.id)
    .join(Service, ServiceUser.service_id == Service.id)
    .filter(Product.order_id == order_id)
    .order_by(Product.id)
    .all()
  )


def assert_order_service_types(order, session):
  session.flush()
  invalid = [product.id for product, _, service in order_service_rows(order.id, session) if service.type != order.type]
  if invalid:
    raise InvalidOrderProductsError(
      f'Ordine {order.id}: i prodotti {invalid} hanno servizi incompatibili con il tipo {order.type.value}.'
    )


def partition_order(order, session):
  """Read-only validation shared by the repair planner and the import writer."""
  rows = order_service_rows(order.id, session)
  if not rows:
    raise InvalidOrderProductsError(f'Ordine {order.id}: nessun servizio valido da importare.')
  if len(rows) != session.query(Product).filter(Product.order_id == order.id).count():
    raise InvalidOrderProductsError(f'Ordine {order.id}: riferimenti prodotto/servizio mancanti.')
  if (
    any(
      product.company_id != order.company_id
      or service_user.company_id != order.company_id
      or service.company_id != order.company_id
      for product, service_user, service in rows
    )
    or len({service_user.user_id for _, service_user, _ in rows}) != 1
  ):
    raise InvalidOrderProductsError(f'Ordine {order.id}: servizi di clienti o attività differenti.')
  groups = defaultdict(list)
  for product, _, service in rows:
    groups[service.type].append(product)
  original_type = order.type if order.type in groups else sorted(groups, key=lambda value: value.name)[0]
  if len(groups) == 1:
    return groups, original_type, {}
  rae_targets = {}
  for product, _, service in rows:
    if product.rae_product_id:
      rae_targets.setdefault(product.rae_product_id, set()).add(service.type)
  for rae_id, types in rae_targets.items():
    rae = session.get(RaeProduct, rae_id)
    shared_elsewhere = (
      session.query(Product.id).filter(Product.rae_product_id == rae_id, Product.order_id != order.id).first()
    )
    if len(types) != 1 or not rae or rae.order_id != order.id or shared_elsewhere:
      raise InvalidOrderProductsError(
        f'Ordine {order.id}: RAEE {rae_id} condiviso; separare quantità e documenti prima della bonifica.'
      )
  return groups, original_type, rae_targets


def split_order_by_service_type(order, session):
  """Keep product IDs and logistics, return original + children; caller commits.
  Money and evidence remain on the original. Shared RAEE records spanning
  partitions must be resolved explicitly, since duplicating them doubles waste.
  """
  lock_order_service_integrity(session)
  session.flush()
  groups, original_type, rae_targets = partition_order(order, session)
  if len(groups) == 1:
    order.type = original_type
    assert_order_service_types(order, session)
    return [order]
  excluded = {
    'id',
    'created_at',
    'updated_at',
    'version',
    'type',
    'external_id',
    'external_link',
    'external_status',
    'mark',
    'signature',
    'motivation',
    'operator_note',
  }
  copied = {
    column.name: getattr(order, column.name) for column in Order.__table__.columns if column.name not in excluded
  }
  links = session.query(ScheduleItemOrder).filter(ScheduleItemOrder.order_id == order.id).all()
  order.type = original_type
  targets = {original_type: order}
  schedule_offsets = defaultdict(int)
  for service_type in sorted(groups, key=lambda value: value.name):
    if service_type == original_type:
      continue
    child = create(
      Order,
      {
        **copied,
        'type': service_type,
        'operator_note': f"Separato da ordine {order.id}. Prove, contrassegno e storico precedenti sull'originale."
        + (f'\nRif. Cliente originale: {order.external_id}' if order.external_id else '')
        + (f'\n{order.operator_note}' if order.operator_note else ''),
      },
      session=session,
    )
    targets[service_type] = child
    for product in groups[service_type]:
      product.order_id = child.id
    for link in links:
      # Completion and driver UI identity belong to ScheduleItem. Sharing the
      # original stop would complete/hide siblings when only one order closes.
      item = session.get(ScheduleItem, link.schedule_item_id)
      schedule_offsets[item.id] += 1
      new_index = item.index + schedule_offsets[item.id]
      for later in (
        session.query(ScheduleItem)
        .filter(ScheduleItem.schedule_id == item.schedule_id, ScheduleItem.index >= new_index)
        .order_by(ScheduleItem.index.desc())
      ):
        later.index += 1
      copied_item = {
        column.name: getattr(item, column.name)
        for column in ScheduleItem.__table__.columns
        if column.name not in {'id', 'created_at', 'updated_at', 'index'}
      }
      child_item = create(ScheduleItem, {**copied_item, 'index': new_index}, session=session)
      create(
        ScheduleItemOrder,
        {
          'company_id': order.company_id,
          'order_id': child.id,
          'schedule_item_id': child_item.id,
        },
        session=session,
      )
  for rae_id, types in rae_targets.items():
    session.get(RaeProduct, rae_id).order_id = targets[next(iter(types))].id
  # Also bumps the original's version when its type stays unchanged.
  child_ids = ', '.join(str(child.id) for child in targets.values() if child.id != order.id)
  order.operator_note = (order.operator_note or '') + f'\nOrdini separati per tipo di servizio: {child_ids}.'
  session.flush()
  for target in targets.values():
    assert_order_service_types(target, session)
  return list(targets.values())

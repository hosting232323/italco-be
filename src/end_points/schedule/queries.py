from datetime import datetime
from sqlalchemy import and_, desc, or_, cast, text, Date
from sqlalchemy.orm import Session as session_type

from database_api import Session
from ...utils.date import handle_date
from ...database.enum import ScheduleType, ScheduleItemUserType, UserRole
from database_api.operations import create, db_session_decorator
from ...database.schema import (
  Schedule,
  User,
  Order,
  DeliveryGroup,
  Transport,
  ScheduleItem,
  ScheduleItemCollectionPoint,
  ScheduleItemOrder,
  ScheduleItemUser,
  CollectionPoint,
  Product,
  ServiceUser,
  Service,
)


# Le join che la query degli id sa aggiungere, con la loro clausola ON.
_ID_QUERY_JOINS = {
  'delivery_group': (DeliveryGroup, DeliveryGroup.schedule_id == Schedule.id),
  'user': (User, DeliveryGroup.user_id == User.id),
  'schedule_item': (ScheduleItem, ScheduleItem.schedule_id == Schedule.id),
  'schedule_item_order': (
    ScheduleItemOrder,
    and_(ScheduleItem.operation_type == ScheduleType.ORDER, ScheduleItemOrder.schedule_item_id == ScheduleItem.id),
  ),
  'order': (Order, ScheduleItemOrder.order_id == Order.id),
  'product': (Product, Order.id == Product.order_id),
  'schedule_item_collection_point': (
    ScheduleItemCollectionPoint,
    and_(
      ScheduleItem.operation_type == ScheduleType.COLLECTIONPOINT,
      ScheduleItemCollectionPoint.schedule_item_id == ScheduleItem.id,
    ),
  ),
  'collection_point': (CollectionPoint, CollectionPoint.id == ScheduleItemCollectionPoint.collection_point_id),
}

# Per ogni modello filtrabile che non sta su schedule, le join da attraversare
# per arrivarci, in ordine di dipendenza. Le chiavi sono i nomi che il frontend
# manda dentro filter['model']; chi non compare qui si filtra su schedule.
_FILTER_MODEL_JOINS = {
  'DeliveryGroup': ('delivery_group',),
  'User': ('delivery_group', 'user'),
  'ScheduleItem': ('schedule_item',),
  'ScheduleItemOrder': ('schedule_item', 'schedule_item_order'),
  'Order': ('schedule_item', 'schedule_item_order', 'order'),
  'Product': ('schedule_item', 'schedule_item_order', 'order', 'product'),
  'ScheduleItemCollectionPoint': ('schedule_item', 'schedule_item_collection_point'),
  'CollectionPoint': ('schedule_item', 'schedule_item_collection_point', 'collection_point'),
}


def _apply_filters(query, filters: list):
  for filter in filters:
    model = globals()[filter['model']]
    field = getattr(model, filter['field'])
    value = filter['value']

    if field in [Schedule.created_at, Schedule.date, Schedule.updated_at] and type(value) is list:
      query = query.filter(field >= handle_date(value[0]), field <= handle_date(value[1]))
    elif field in [Schedule.created_at, Schedule.updated_at]:
      query = query.filter(cast(field, Date) == value)
    else:
      query = query.filter(field == value)

  return query


def query_schedule_ids(filters: list, limit: int, session: session_type) -> list[int]:
  """Gli id dei borderò da mostrare, scelti senza passare dalla join di dettaglio.

  La join di dettaglio moltiplica item x prodotti x utenti delivery: farla girare
  su tutto lo storico dell'attività solo per scoprire quali sono gli ultimi
  `limit` borderò costa quanto l'intero archivio, e su un'attività grande vuol
  dire minuti di query e il worker ucciso da gunicorn. Qui resta solo quello che
  serve a scegliere: transport, che è uno a uno con il borderò e non moltiplica
  niente, e le tabelle nominate dai filtri.

  Le inner join su schedule_item e delivery_group della query di dettaglio
  scartano i borderò senza item o senza assegnatari: quel taglio va riprodotto,
  ma come EXISTS, che non moltiplica le righe. Le outer join verso ordini,
  prodotti e punti di ritiro invece non scartano niente, quindi qui non servono
  e vengono aggiunte solo se un filtro le nomina.
  """
  query = session.query(Schedule.id).join(Transport, Schedule.transport_id == Transport.id)

  joined = set()
  for filter in filters:
    for name in _FILTER_MODEL_JOINS.get(filter['model'], ()):
      if name in joined:
        continue
      joined.add(name)
      query = query.join(*_ID_QUERY_JOINS[name])

  if 'schedule_item' not in joined:
    query = query.filter(session.query(ScheduleItem).filter(ScheduleItem.schedule_id == Schedule.id).exists())
  if 'delivery_group' not in joined:
    query = query.filter(
      session.query(DeliveryGroup)
      .join(User, DeliveryGroup.user_id == User.id)
      .filter(DeliveryGroup.schedule_id == Schedule.id)
      .exists()
    )

  query = _apply_filters(query, filters)
  # Il GROUP BY serve solo a deduplicare quello che moltiplicano le join dei
  # filtri: senza join non ha niente da fare e impedisce a Postgres di prendere
  # i primi `limit` borderò dall'indice invece di aggregare tutto l'archivio.
  if joined:
    query = query.group_by(Schedule.id)

  return [row[0] for row in query.order_by(desc(Schedule.created_at)).limit(limit)]


def query_schedules(
  filters: list, limit: int = None, get_services: bool = False
) -> list[tuple[Schedule, Transport, ScheduleItem, CollectionPoint, Order, Product, User, Service]]:
  with Session() as session:
    entities = [Schedule, Transport, ScheduleItem, CollectionPoint, Order, Product, User]
    if get_services:
      entities.append(Service)

    query = (
      session.query(*entities)
      .join(Transport, Schedule.transport_id == Transport.id)
      .join(ScheduleItem, ScheduleItem.schedule_id == Schedule.id)
      .outerjoin(
        ScheduleItemCollectionPoint,
        and_(
          ScheduleItem.operation_type == ScheduleType.COLLECTIONPOINT,
          ScheduleItemCollectionPoint.schedule_item_id == ScheduleItem.id,
        ),
      )
      .outerjoin(CollectionPoint, CollectionPoint.id == ScheduleItemCollectionPoint.collection_point_id)
      .outerjoin(
        ScheduleItemOrder,
        and_(ScheduleItem.operation_type == ScheduleType.ORDER, ScheduleItemOrder.schedule_item_id == ScheduleItem.id),
      )
      .outerjoin(Order, ScheduleItemOrder.order_id == Order.id)
      .outerjoin(Product, Order.id == Product.order_id)
      .join(DeliveryGroup, DeliveryGroup.schedule_id == Schedule.id)
      .join(User, DeliveryGroup.user_id == User.id)
    )
    if get_services:
      query = query.outerjoin(ServiceUser, Product.service_user_id == ServiceUser.id).outerjoin(
        Service, ServiceUser.service_id == Service.id
      )

    query = _apply_filters(query, filters)

    # Senza limite non c'è niente da scegliere: i filtri sulla query di dettaglio
    # bastano già, e il giro sugli id sarebbe solo una query in più.
    if limit is not None:
      ids = query_schedule_ids(filters, limit, session)
      if not ids:
        return []
      query = query.filter(Schedule.id.in_(ids))

    return query.order_by(desc(Schedule.created_at)).all()


@db_session_decorator(commit=False)
def query_invalid_delivery_user_ids(user_ids: list[int], session: session_type = None) -> list[int]:
  """Ritorna gli id che non corrispondono a utenti con ruolo DELIVERY."""
  valid_ids = {row[0] for row in session.query(User.id).filter(User.id.in_(user_ids), User.role == UserRole.DELIVERY)}
  return sorted(set(user_ids) - valid_ids)


def delivery_assignment_lock_key(user_id: int, schedule_date) -> str:
  return f'delivery-assignment:{user_id}:{str(schedule_date)[:10]}'


def lock_delivery_assignment(user_id: int, schedule_date, session: session_type):
  """Serializza il check-then-create dei DeliveryGroup per (utente, data).

  Il lock advisory è transazionale: viene rilasciato al commit/rollback
  della sessione, quindi due richieste concorrenti non possono superare
  entrambe il controllo query_schedules_count per la stessa coppia.
  """
  session.execute(
    text('SELECT pg_advisory_xact_lock(hashtext(:key))'),
    {'key': delivery_assignment_lock_key(user_id, schedule_date)},
  )


@db_session_decorator(commit=False)
def query_schedules_count(
  user_id: int,
  schedule_date: datetime,
  exclude_schedule_id: int = None,
  session: session_type = None,
) -> int:
  query = session.query(DeliveryGroup).join(
    Schedule,
    and_(DeliveryGroup.schedule_id == Schedule.id, DeliveryGroup.user_id == user_id, Schedule.date == schedule_date),
  )
  if exclude_schedule_id is not None:
    query = query.filter(Schedule.id != exclude_schedule_id)
  return query.count()


@db_session_decorator(commit=False)
def get_schedule_item_by_order(order: Order, session: session_type = None) -> ScheduleItem:
  return (
    session.query(ScheduleItem)
    .join(Schedule, Schedule.id == ScheduleItem.schedule_id)
    .join(
      ScheduleItemOrder,
      and_(
        ScheduleItemOrder.order_id == order.id,
        ScheduleItem.operation_type == ScheduleType.ORDER,
        ScheduleItemOrder.schedule_item_id == ScheduleItem.id,
      ),
    )
    .order_by(desc(Schedule.date), desc(Schedule.id), desc(ScheduleItem.id))
    .first()
  )


@db_session_decorator(commit=False)
def get_schedule_by_order(order_id: int, session: session_type = None) -> Schedule:
  return (
    session.query(Schedule)
    .join(ScheduleItem, Schedule.id == ScheduleItem.schedule_id)
    .join(
      ScheduleItemOrder,
      and_(
        ScheduleItemOrder.order_id == order_id,
        ScheduleItem.operation_type == ScheduleType.ORDER,
        ScheduleItemOrder.schedule_item_id == ScheduleItem.id,
      ),
    )
    .order_by(desc(Schedule.date), desc(Schedule.id))
    .first()
  )


def format_query_result(
  tupla: tuple[Schedule, Transport, ScheduleItem, CollectionPoint, Order, Product, User, Service],
  list: list[dict],
) -> list[dict]:
  for element in list:
    if element['id'] == tupla[0].id:
      format_schedule_item(
        element['schedule_items'], tupla[2], tupla[3], tupla[4], tupla[5], tupla[7] if len(tupla) == 8 else None
      )
      if tupla[6] and tupla[6].id not in [user['id'] for user in element['users']]:
        element['users'].append(tupla[6].format_user())
      return list

  schedule = {
    **tupla[0].to_dict(),
    'transport': tupla[1].to_dict(),
    'users': [tupla[6].format_user()] if tupla[6] else [],
    'schedule_items': [],
  }
  format_schedule_item(
    schedule['schedule_items'], tupla[2], tupla[3], tupla[4], tupla[5], tupla[7] if len(tupla) == 8 else None
  )
  list.append(schedule)
  return list


def get_schedule_item_for_order_id_filter(
  schedule_id: int,
) -> list[tuple[Schedule, ScheduleItem, CollectionPoint, Order, Product]]:
  with Session() as session:
    return (
      session.query(Schedule, ScheduleItem, CollectionPoint, Order, Product)
      .join(ScheduleItem, and_(ScheduleItem.schedule_id == Schedule.id, Schedule.id == schedule_id))
      .outerjoin(
        ScheduleItemCollectionPoint,
        and_(
          ScheduleItem.operation_type == ScheduleType.COLLECTIONPOINT,
          ScheduleItemCollectionPoint.schedule_item_id == ScheduleItem.id,
        ),
      )
      .outerjoin(CollectionPoint, CollectionPoint.id == ScheduleItemCollectionPoint.collection_point_id)
      .outerjoin(
        ScheduleItemOrder,
        and_(ScheduleItem.operation_type == ScheduleType.ORDER, ScheduleItemOrder.schedule_item_id == ScheduleItem.id),
      )
      .outerjoin(Order, ScheduleItemOrder.order_id == Order.id)
      .outerjoin(Product, Order.id == Product.order_id)
      .all()
    )


def format_schedule_item(
  schedule_items: list,
  schedule_item: ScheduleItem,
  collection_point: CollectionPoint,
  order: Order,
  product: Product,
  service: Service,
):
  if schedule_item.operation_type == ScheduleType.ORDER and order and product:
    schedule_item_order = next(
      (item for item in schedule_items if 'order_id' in item and item['order_id'] == order.id), None
    )
    product_dict = {}
    if product.collection_point_id:
      product_dict = {'collection_point': {'id': product.collection_point_id}}
    elif product.transport_id:
      product_dict = {'transport': {'id': product.transport_id}}

    if service:
      product_dict['services'] = [service.name]
    if not schedule_item_order:
      item = order.to_dict()
      item['order_id'] = order.id
      item['products'] = {product.name: product_dict}
    elif product.name not in schedule_item_order['products']:
      schedule_item_order['products'][product.name] = product_dict
      return
    elif service and service.name not in schedule_item_order['products'][product.name]['services']:
      schedule_item_order['products'][product.name]['services'].append(service.name)
      return
    else:
      return

  elif (
    schedule_item.operation_type == ScheduleType.COLLECTIONPOINT
    and collection_point
    and collection_point.id
    not in [item['collection_point_id'] for item in schedule_items if 'collection_point_id' in item]
  ):
    item = collection_point.to_dict()
    item['collection_point_id'] = collection_point.id
  else:
    return

  item['id'] = schedule_item.id
  item['index'] = schedule_item.index
  item['completed'] = schedule_item.completed
  item['operation_type'] = schedule_item.operation_type.value
  item['end_time_slot'] = schedule_item.end_time_slot.strftime('%H:%M:%S')
  item['start_time_slot'] = schedule_item.start_time_slot.strftime('%H:%M:%S')
  schedule_items.append(item)


@db_session_decorator(commit=False)
def get_schedule_items(
  schedule: Schedule, session: session_type = None
) -> list[tuple[ScheduleItem, ScheduleItemCollectionPoint, ScheduleItemOrder]]:
  return (
    session.query(ScheduleItem, ScheduleItemCollectionPoint, ScheduleItemOrder)
    .outerjoin(
      ScheduleItemCollectionPoint,
      and_(
        ScheduleItem.schedule_id == schedule.id,
        ScheduleItemCollectionPoint.schedule_item_id == ScheduleItem.id,
        ScheduleItem.operation_type == ScheduleType.COLLECTIONPOINT,
      ),
    )
    .outerjoin(
      ScheduleItemOrder,
      and_(
        ScheduleItem.schedule_id == schedule.id,
        ScheduleItemOrder.schedule_item_id == ScheduleItem.id,
        ScheduleItem.operation_type == ScheduleType.ORDER,
      ),
    )
    .filter(ScheduleItem.schedule_id == schedule.id)
    .all()
  )


@db_session_decorator(commit=False)
def get_delivery_groups(schedule: Schedule, session: session_type = None) -> list[DeliveryGroup]:
  return session.query(DeliveryGroup).filter(DeliveryGroup.schedule_id == schedule.id).all()


@db_session_decorator(commit=False)
def get_schedule_item_users(schedule: Schedule, session: session_type = None) -> list[ScheduleItemUser]:
  return session.query(ScheduleItemUser).filter(ScheduleItemUser.schedule_id == schedule.id).all()


@db_session_decorator(commit=False)
def get_latest_schedule_item_user(schedule_id: int, session: session_type = None) -> ScheduleItemUser:
  """L'evento più recente per il borderò: determina chi tiene la posizione."""
  return (
    session.query(ScheduleItemUser)
    .filter(ScheduleItemUser.schedule_id == schedule_id)
    .order_by(desc(ScheduleItemUser.id))
    .first()
  )


def close_schedule_position_if_done(schedule_item: ScheduleItem, session: session_type = None):
  """Se tutti gli item del borderò sono completati, chiude la posizione condivisa.

  Va chiamata subito dopo aver marcato `schedule_item` come completato, sia dal
  completamento di un punto di ritiro sia dalla chiusura di un ordine.
  """
  if session is None:
    _close_schedule_position_if_done(schedule_item.schedule_id)
  else:
    _close_schedule_position_if_done(schedule_item.schedule_id, session=session)


@db_session_decorator(commit=True)
def _close_schedule_position_if_done(schedule_id: int, session: session_type = None):
  remaining = (
    session.query(ScheduleItem)
    .filter(ScheduleItem.schedule_id == schedule_id, ScheduleItem.completed.is_(False))
    .count()
  )
  if remaining > 0:
    return

  latest = get_latest_schedule_item_user(schedule_id, session=session)
  if latest is None or latest.type == ScheduleItemUserType.CLOSING:
    return

  create(
    ScheduleItemUser,
    {'schedule_id': schedule_id, 'user_id': latest.user_id, 'type': ScheduleItemUserType.CLOSING},
    session=session,
  )


def get_delivery_groups_by_order_id(order_id: int) -> list[DeliveryGroup]:
  with Session() as session:
    return (
      session.query(DeliveryGroup)
      .join(
        Schedule,
        DeliveryGroup.schedule_id == Schedule.id,
      )
      .join(
        ScheduleItem,
        ScheduleItem.schedule_id == Schedule.id,
      )
      .join(
        ScheduleItemOrder,
        and_(
          ScheduleItemOrder.schedule_item_id == ScheduleItem.id,
          ScheduleItemOrder.order_id == order_id,
          ScheduleItem.operation_type == ScheduleType.ORDER,
        ),
      )
      .all()
    )


def get_delivery_users_by_date(date: datetime) -> list[User]:
  with Session() as session:
    return (
      session.query(User)
      .outerjoin(DeliveryGroup, User.id == DeliveryGroup.user_id)
      .outerjoin(Schedule, Schedule.id == DeliveryGroup.schedule_id)
      .filter(or_(Schedule.date != date, Schedule.id.is_(None)), User.role == UserRole.DELIVERY)
      .all()
    )


def get_transports_by_date(date: datetime) -> list[Transport]:
  with Session() as session:
    return (
      session.query(Transport)
      .outerjoin(Schedule, Schedule.transport_id == Transport.id)
      .filter(or_(Schedule.date != date, Schedule.id.is_(None)))
      .all()
    )

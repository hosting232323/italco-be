from datetime import datetime

from .utils import parse_time
from database_api import Session
from ..users.queries import get_user_info
from .api import save_order_status_to_euronics
from ..service.queries import get_service_users
from .services import create_products, update_products
from database_api.operations import create, update, get_by_id, delete
from .queries import query_orders, format_query_result, get_delivery_user
from ...database.enum import OrderStatus, UserRole, OrderType, EuronicsStatus
from ...database.schema import User, Order, Motivation, DeliveryUserInfo, ServiceUser
from .clone import format_data_cloning_order, update_cloned_order, query_products, reschedule_products
from ..schedule.queries import get_delivery_groups_by_order_id, get_schedule_item_by_order, get_schedule_by_order


NON_UPDATABLE_ORDER_FIELDS = frozenset(
  {
    'products',
    'user_id',
    'motivation',
    'start_time_slot',
    'end_time_slot',
    'version',
    'id',
    'created_at',
    'updated_at',
  }
)


def create_order(user: User, data: dict):
  clean_data = {key: value for key, value in data.items() if key not in ['products', 'user_id', 'cloned_order_id']}
  clean_data['type'] = OrderType(clean_data['type'])
  if 'external_status' in clean_data:
    clean_data['external_status'] = EuronicsStatus(clean_data['external_status'])
  if user.role in [UserRole.ADMIN, UserRole.OPERATOR]:
    clean_data['confirmed'] = True
    clean_data['confirmation_date'] = datetime.now()
    if 'booking_date' in clean_data and clean_data['booking_date'] is not None:
      clean_data['status'] = OrderStatus.BOOKED

  with Session() as session:
    cloned_order = False
    if 'cloned_order_id' in data and data['cloned_order_id']:
      cloned_order = True
      clean_data = format_data_cloning_order(clean_data, data['cloned_order_id'])

    order: Order = create(Order, clean_data, session=session)
    create_products(
      order,
      data['products'],
      user.id if user.role == UserRole.CUSTOMER else data['user_id'],
      cloned_order,
      session=session,
    )
    if cloned_order:
      update_cloned_order(order, data['cloned_order_id'], session=session)

    session.commit()
    save_order_status_to_euronics(order)
  return {'status': 'ok', 'order': order.to_dict()}


def filter_orders(filters: dict, customer_id: int = None):
  orders = []
  for tupla in query_orders(filters, 500, customer_id):
    orders = format_query_result(tupla, orders)
  return {'status': 'ok', 'orders': orders}


def get_order(order_id: int):
  orders = []
  for tupla in query_orders([{'model': 'Order', 'field': 'id', 'value': order_id}]):
    orders = format_query_result(tupla, orders)
  if len(orders) != 1:
    raise Exception('Numero di ordini trovati non valido')

  if orders[0]['status'] == 'Booking':
    for delivery_group in get_delivery_groups_by_order_id(orders[0]['id']):
      delivery_user_info = get_user_info(delivery_group.user_id, DeliveryUserInfo)
      if delivery_user_info and delivery_user_info.lat is not None and delivery_user_info.lon is not None:
        orders[0]['lat'] = delivery_user_info.lat
        orders[0]['lon'] = delivery_user_info.lon
        break

  return {'status': 'ok', 'order': orders[0]}


def delete_order(user: User, order_id: int):
  with Session() as session:
    order: Order = get_by_id(Order, order_id, session=session)
    item = get_schedule_item_by_order(order, session=session) if order else None
    if not order or item or order.status not in [OrderStatus.ACQUIRED, OrderStatus.BOOKED]:
      return {
        'status': 'ko',
        'message': "Si necessità un ordine in stato di attesa senza borderò per procedere con l'eliminazione",
      }

    delete(order, session=session)
    session.commit()
  return {'status': 'ok', 'message': 'Operazione completata'}


def update_order(user: User, order: Order, data: dict, session, pending_sms: list = None):
  is_delay = data['delay'] if 'delay' in data else False
  schedule_item = get_schedule_item_by_order(order, session=session)
  if 'motivation' in data:
    motivation = create(
      Motivation,
      {
        'delay': is_delay,
        'order_id': data['id'],
        'status': OrderStatus(data['status']),
        'anomaly': data['anomaly'] if 'delay' in data else False,
        'text': data['motivation'],
      },
      session=session,
    )
  else:
    motivation = None

  if 'status' in data:
    data['status'] = OrderStatus(data['status'])
    if data['status'] in [OrderStatus.NOT_DELIVERED, OrderStatus.DELIVERED] and not order.completion_date:
      data['completion_date'] = datetime.now()
    if data['status'] in [OrderStatus.NOT_DELIVERED, OrderStatus.DELIVERED, OrderStatus.TO_RESCHEDULE]:
      if schedule_item:
        update(schedule_item, {'completed': True}, session=session)
  if order.status == OrderStatus.ACQUIRED and 'booking_date' in data and order.booking_date != data['booking_date']:
    data['status'] = OrderStatus.BOOKED

  if 'type' in data:
    data['type'] = OrderType(data['type'])
  if 'confirmed' in data and data['confirmed'] and not order.confirmation_date:
    data['confirmation_date'] = datetime.now()
  if 'external_status' in data:
    del data['external_status']

  if 'products' in data:
    if user.role != UserRole.DELIVERY:
      update_products(
        order,
        data['products'],
        user.id if user.role == UserRole.CUSTOMER else data['user_id'],
        get_schedule_by_order(order.id, session=session) if schedule_item else None,
        session,
      )
    if 'status' in data and data['status'] == OrderStatus.TO_RESCHEDULE and order.status != OrderStatus.TO_RESCHEDULE:
      reschedule_products(
        get_delivery_user(order, session=session).id if user.role != UserRole.DELIVERY else user.id,
        order,
        data['products'],
        session,
      )

  if schedule_item and 'start_time_slot' in data and 'end_time_slot' in data:
    if (
      parse_time(data['start_time_slot']) != schedule_item.start_time_slot
      or parse_time(data['end_time_slot']) != schedule_item.end_time_slot
    ):
      update(
        schedule_item,
        {'start_time_slot': data['start_time_slot'], 'end_time_slot': data['end_time_slot']},
        session=session,
      )
      # L'SMS parte dopo il commit (dal chiamante): un rollback successivo non
      # deve lasciare il cliente con una riprogrammazione mai avvenuta.
      if pending_sms is not None:
        pending_sms.append((order, schedule_item))

  order = update(
    order,
    {key: value for key, value in data.items() if key not in NON_UPDATABLE_ORDER_FIELDS},
    session=session,
  )
  return motivation


def update_order_customer(user: User, user_id: int, order_id: int):
  with Session() as session:
    updates = []
    service_users = get_service_users(user_id, session=session)
    order = get_by_id(Order, order_id, session=session)
    products = query_products(order, session=session)
    for product in products:
      old_service_user: ServiceUser = get_by_id(ServiceUser, product.service_user_id, session=session)
      service_user = next(
        (service_user for service_user in service_users if service_user.service_id == old_service_user.service_id), None
      )
      if service_user:
        updates.append((product, service_user))
    if len(updates) != len(products):
      return {'status': 'ko', 'message': "Il nuovo utente non possiete gli stessi servizi dell'utente precedente"}

    for product, service_user in updates:
      update(product, {'service_user_id': service_user.id}, session=session)
    session.commit()
  return {'status': 'ok', 'message': 'Operazione completata'}

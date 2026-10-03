from datetime import datetime
import hashlib

from ...order_integrity import assert_order_service_types, lock_order_service_integrity

from .utils import parse_time
from database_api import Session
from ... import STATIC_FOLDER
from ..users.queries import get_user_info
from api.storage.session import SessionWithStorage
from .api import save_order_status_to_euronics
from ..service.queries import get_service_users
from .services import create_products, update_products
from database_api.operations import create, update, get_by_id, delete
from .queries import query_orders, format_query_result, get_order_by_tracking_token
from ...database.enum import OrderStatus, UserRole, OrderType, EuronicsStatus, ScheduleItemUserType
from ...database.schema import User, Order, DeliveryUserInfo, ServiceUser, CollectionPoint
from .clone import format_data_cloning_order, update_cloned_order, query_products, reschedule_products
from ..schedule.queries import (
  get_schedule_item_by_order,
  get_schedule_by_order,
  close_schedule_position_if_done,
  get_latest_schedule_item_user,
)


NON_UPDATABLE_ORDER_FIELDS = frozenset(
  {
    'products',
    'user_id',
    'company_id',
    'start_time_slot',
    'end_time_slot',
    'version',
    'id',
    'created_at',
    'updated_at',
  }
)

ROLE_UPDATABLE_ORDER_FIELDS = {
  UserRole.CUSTOMER: frozenset(
    {
      'addressee',
      'address',
      'cap',
      'floor',
      'elevator',
      'addressee_contact',
      'customer_note',
      'drc',
      'products',
      'version',
    }
  ),
  UserRole.DELIVERY: frozenset(
    {
      'status',
      'anomaly',
      'delay',
      'motivation',
      'start_time_slot',
      'end_time_slot',
      'photos',
      'signature',
      'mark',
      'products',
      'version',
    }
  ),
}


def restrict_order_update(user: User, data: dict, session) -> dict:
  allowed = ROLE_UPDATABLE_ORDER_FIELDS.get(user.role)
  if allowed is None:
    return data

  restricted = {key: value for key, value in data.items() if key in allowed}
  if user.role == UserRole.DELIVERY and isinstance(restricted.get('products'), dict):
    safe_products = {}
    for name, details in restricted['products'].items():
      if not isinstance(details, dict) or 'release_collection_point_id' not in details:
        continue
      collection_point_id = details['release_collection_point_id']
      if collection_point_id == 0:
        safe_products[name] = {'release_collection_point_id': 0}
      elif (
        isinstance(collection_point_id, int)
        and session.query(CollectionPoint.id).filter(CollectionPoint.id == collection_point_id).first()
      ):
        safe_products[name] = {'release_collection_point_id': collection_point_id}
    restricted['products'] = safe_products
  return restricted


def create_order(user: User, data: dict):
  clean_data = {key: value for key, value in data.items() if key not in ['products', 'user_id', 'cloned_order_id']}
  if not clean_data.get('address'):
    return {'status': 'ko', 'message': "L'indirizzo è obbligatorio"}
  clean_data['type'] = OrderType(clean_data['type'])
  if 'external_status' in clean_data:
    clean_data['external_status'] = EuronicsStatus(clean_data['external_status'])
  # Il super admin che opera dentro una company vale quanto un admin: l'ordine
  # che crea nasce confermato, come per admin e operatori (stesso bypass che
  # flask_session_authentication fa sul controllo di ruolo).
  if user.role in [UserRole.ADMIN, UserRole.OPERATOR, UserRole.SUPER_ADMIN]:
    clean_data['confirmed'] = True
    clean_data['confirmation_date'] = datetime.now()
    if 'booking_date' in clean_data and clean_data['booking_date'] is not None:
      clean_data['status'] = OrderStatus.BOOKED

  with Session() as session:
    lock_order_service_integrity(session)
    cloned_order = False
    if 'cloned_order_id' in data and data['cloned_order_id']:
      cloned_order = True
      clean_data = format_data_cloning_order(clean_data, data['cloned_order_id'])

    missing = [field for field in ('type', 'addressee', 'address', 'cap', 'dpc', 'drc') if not clean_data.get(field)]
    if missing:
      return {'status': 'ko', 'message': f'Campi obbligatori mancanti: {", ".join(missing)}'}

    order: Order = create(Order, clean_data, session=session)
    create_products(
      order,
      data.get('products'),
      user.id if user.role == UserRole.CUSTOMER else data['user_id'],
      cloned_order,
      session=session,
    )
    assert_order_service_types(order, session)
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


def get_order(order_id: int, customer_id: int = None):
  orders = []
  for tupla in query_orders([{'model': 'Order', 'field': 'id', 'value': order_id}], customer_id=customer_id):
    orders = format_query_result(tupla, orders)
  if len(orders) != 1:
    raise Exception('Numero di ordini trovati non valido')

  if orders[0]['status'] == 'Booking':
    schedule = get_schedule_by_order(order_id)
    holder = get_latest_schedule_item_user(schedule.id) if schedule else None
    if holder and holder.type != ScheduleItemUserType.CLOSING:
      delivery_user_info = get_user_info(holder.user_id, DeliveryUserInfo)
      if delivery_user_info and delivery_user_info.lat is not None and delivery_user_info.lon is not None:
        orders[0]['lat'] = delivery_user_info.lat
        orders[0]['lon'] = delivery_user_info.lon

  return {'status': 'ok', 'order': orders[0]}


def get_public_order(token: str):
  token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
  order = get_order_by_tracking_token(token_hash)
  if not order:
    return None

  full_order = get_order(order.id)['order']
  public_order = {
    key: full_order[key]
    for key in (
      'id',
      'status',
      'addressee',
      'address',
      'addressee_contact',
      'dpc',
      'drc',
      'booking_date',
      'delivery_slot_start',
      'delivery_slot_end',
      'lat',
      'lon',
    )
    if key in full_order
  }
  public_order['user'] = {'nickname': full_order.get('user', {}).get('nickname')}
  public_order['products'] = {
    name: {
      'services': [
        {'name': service.get('name'), 'type': service.get('type')} for service in details.get('services', [])
      ]
    }
    for name, details in full_order.get('products', {}).items()
  }
  return {'status': 'ok', 'order': public_order}


def delete_order(user: User, order_id: int):
  with SessionWithStorage() as session:
    order: Order = get_by_id(Order, order_id, session=session)
    item = get_schedule_item_by_order(order, session=session) if order else None
    if not order or item or order.status not in [OrderStatus.ACQUIRED, OrderStatus.BOOKED]:
      return {
        'status': 'ko',
        'message': "Si necessità un ordine in stato di attesa senza borderò per procedere con l'eliminazione",
      }

    for photo in order.photo:
      session.delete_file(photo.link.rsplit('/', 1)[-1], STATIC_FOLDER, subfolder='photos')
    delete(order, session=session)
    session.commit()
  return {'status': 'ok', 'message': 'Operazione completata'}


def update_order(user: User, order: Order, data: dict, session, pending_sms: list = None):
  lock_order_service_integrity(session)
  motivation = data.get('motivation')
  schedule_item = get_schedule_item_by_order(order, session=session)

  if 'status' in data:
    data['status'] = OrderStatus(data['status'])
    if data['status'] in [OrderStatus.NOT_DELIVERED, OrderStatus.DELIVERED] and not order.completion_date:
      data['completion_date'] = datetime.now()
    if data['status'] in [OrderStatus.NOT_DELIVERED, OrderStatus.DELIVERED, OrderStatus.TO_RESCHEDULE]:
      if schedule_item:
        schedule_item = update(schedule_item, {'completed': True}, session=session)
        close_schedule_position_if_done(schedule_item, session=session)
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
        order_type=data.get('type', order.type),
      )
    if 'status' in data and data['status'] == OrderStatus.TO_RESCHEDULE and order.status != OrderStatus.TO_RESCHEDULE:
      reschedule_products(order, data['products'], session)

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
  assert_order_service_types(order, session)
  return motivation


def update_order_customer(user: User, user_id: int, order_id: int):
  with Session() as session:
    lock_order_service_integrity(session)
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
    assert_order_service_types(order, session)
    session.commit()
  return {'status': 'ok', 'message': 'Operazione completata'}

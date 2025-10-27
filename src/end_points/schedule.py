import os
from hashids import Hashids
from sqlalchemy import and_
from datetime import datetime
from flask import Blueprint, request

from .. import IS_DEV
from api.sms import send_sms
from database_api import Session
from ..database.enum import UserRole, OrderStatus
from .users.session import flask_session_authentication
from database_api.operations import create, delete, get_by_id, update, get_by_ids
from ..database.schema import Schedule, User, Order, DeliveryGroup, Transport, ServiceUser, OrderServiceUser


schedule_bp = Blueprint('schedule_bp', __name__)
hashids = Hashids(salt='mia-chiave-segreta-super-segreta', min_length=8)


@schedule_bp.route('', methods=['POST'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN])
def create_schedule(user: User):
  orders, orders_data_map, schedule_data, users, response = format_schedule_data(request.json)
  if response:
    return response

  schedule = create(Schedule, schedule_data)
  for user in users:
    if query_schedules_count(user['id'], schedule.date) == 0:
      create(DeliveryGroup, {'schedule_id': schedule.id, 'user_id': user['id']})

  for order in orders:
    if order.id in orders_data_map:
      data_update = orders_data_map[order.id]
      order = update(
        order,
        {
          'schedule_id': schedule.id,
          'status': OrderStatus.IN_PROGRESS,
          'start_time_slot': data_update['start_time_slot'],
          'end_time_slot': data_update['end_time_slot'],
          'schedule_index': data_update['schedule_index'],
          'assignament_date': datetime.now(),
        },
      )
      send_schedule_sms(order)
  return {'status': 'ok', 'schedule': schedule.to_dict()}


@schedule_bp.route('<id>', methods=['DELETE'])
@flask_session_authentication([UserRole.ADMIN])
def delete_schedule(user: User, id):
  schedule = get_by_id(Schedule, int(id))
  orders = get_related_orders(schedule)
  for delivery_group in get_delivery_groups(schedule):
    delete(delivery_group)
  delete(schedule)
  for order in orders:
    update(order, {'schedule_id': None, 'assignament_date': None, 'status': OrderStatus.PENDING})
  return {'status': 'ok', 'message': 'Operazione completata'}


@schedule_bp.route('', methods=['GET'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN])
def get_schedules(user: User):
  schedules = []
  for tupla in query_schedules():
    schedules = format_query_result(tupla, schedules)
  return {'status': 'ok', 'schedules': schedules}


@schedule_bp.route('<id>', methods=['PUT'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN])
def update_schedule(user: User, id):
  if 'deleted_orders' in request.json:
    for order in get_by_ids(Order, request.json['deleted_orders']):
      update(order, {'schedule_id': None, 'assignament_date': None, 'status': OrderStatus.PENDING})
    del request.json['deleted_orders']

  schedule: Schedule = get_by_id(Schedule, int(id))
  delivery_groups = get_delivery_groups(schedule)
  deleted_users = []
  if 'deleted_users' in request.json:
    deleted_users = request.json['deleted_users']
    for user_id in deleted_users:
      for delivery_group in delivery_groups:
        if delivery_group.user_id == user_id:
          delete(delivery_group)
          break
    del request.json['deleted_users']

  orders, orders_data_map, schedule_data, users, response = format_schedule_data(request.json)
  if response:
    return response

  schedule = update(schedule, schedule_data)
  actual_user_ids = list(set([delivery_group.user_id for delivery_group in delivery_groups]) - set(deleted_users))
  for user in users:
    if user['id'] not in actual_user_ids and query_schedules_count(user['id'], schedule.date) == 0:
      create(DeliveryGroup, {'schedule_id': schedule.id, 'user_id': user['id']})

  for order in orders:
    if order.id in orders_data_map:
      data_update = orders_data_map[order.id]
      diff = {
        'schedule_id': schedule.id,
        'start_time_slot': data_update['start_time_slot'],
        'end_time_slot': data_update['end_time_slot'],
        'schedule_index': data_update['schedule_index'],
      }
      if order.status == OrderStatus.PENDING:
        diff['status'] = OrderStatus.IN_PROGRESS
      if not order.assignament_date:
        diff['assignament_date'] = datetime.now()
      order = update(order, diff)
      send_schedule_sms(order)
  return {'status': 'ok', 'schedule': schedule.to_dict()}


def query_schedules(id: int = None) -> list[tuple[Schedule, Transport, Order, User]]:
  with Session() as session:
    query = (
      session.query(Schedule, Transport, Order, User)
      .join(Transport, Schedule.transport_id == Transport.id)
      .outerjoin(Order, Order.schedule_id == Schedule.id)
      .outerjoin(DeliveryGroup, DeliveryGroup.schedule_id == Schedule.id)
      .outerjoin(User, DeliveryGroup.user_id == User.id)
    )
    if id:
      query = query.filter(Schedule.id == id)
    return query.all()


def query_schedules_count(user_id, schedule_date) -> int:
  with Session() as session:
    return (
      session.query(DeliveryGroup)
      .join(
        Schedule,
        and_(
          DeliveryGroup.schedule_id == Schedule.id, DeliveryGroup.user_id == user_id, Schedule.date == schedule_date
        ),
      )
      .count()
    )


def get_related_orders(schedule: Schedule) -> list[Order]:
  with Session() as session:
    return session.query(Order).filter(Order.schedule_id == schedule.id).all()


def format_query_result(tupla: tuple[Schedule, Transport, Order, User], list: list[dict]) -> list[dict]:
  for element in list:
    if element['id'] == tupla[0].id:
      if tupla[2] and tupla[2].id not in [order['id'] for order in element['orders']]:
        element['orders'].append(tupla[2].to_dict())
      if tupla[3] and tupla[3].id not in [user['id'] for user in element['users']]:
        element['users'].append(tupla[3].to_dict())
      return list

  list.append(
    {
      **tupla[0].to_dict(),
      'transport': tupla[1].to_dict(),
      'users': [tupla[3].to_dict()] if tupla[3] else [],
      'orders': [tupla[2].to_dict()] if tupla[2] else [],
    }
  )
  return list


def get_selling_point(order: Order) -> str:
  with Session() as session:
    return (
      session.query(User.nickname)
      .join(ServiceUser, User.id == ServiceUser.user_id)
      .join(
        OrderServiceUser,
        and_(ServiceUser.id == OrderServiceUser.service_user_id, OrderServiceUser.order_id == order.id),
      )
      .scalar()
    )


def format_schedule_data(schedule_data: dict) -> list[list[Order], dict]:
  orders_data = schedule_data['orders']
  orders: list[Order] = get_by_ids(Order, [o['id'] for o in orders_data])
  if not orders:
    return None, None, None, None, {'status': 'ko', 'error': 'Errore nella creazione del borderò'}

  del schedule_data['orders']
  if 'order_ids' in schedule_data:
    del schedule_data['order_ids']
  if 'deleted_orders' in schedule_data:
    del schedule_data['deleted_orders']
  if 'transport' in schedule_data:
    del schedule_data['transport']
  users = []
  if 'users' in schedule_data:
    users = schedule_data['users']
    del schedule_data['users']

  orders_data_map = {o['id']: o for o in orders_data}
  return orders, orders_data_map, schedule_data, users, None


def send_schedule_sms(order: Order):
  if not IS_DEV and order.addressee_contact:
    start = order.start_time_slot.strftime('%H:%M')
    end = order.end_time_slot.strftime('%H:%M')
    send_sms(
      os.environ['VONAGE_API_KEY'],
      os.environ['VONAGE_API_SECRET'],
      'Ares',
      order.addressee_contact,
      f'ARES ITALCO.MI - Gentile Cliente, la consegna relativa al Punto Vendita: {get_selling_point(order)}, è programmata per il {order.assignament_date}'
      f", fascia {start} - {end}. Riceverà un preavviso di 30 minuti prima dell'arrivo. Per monitorare ogni f"
      f'ase della sua consegna clicchi il link in questione {get_order_link(order)}. La preghiamo di garantire la presenza e la reperibilit'
      'à al numero indicato. Buona Giornata!',
    )


def get_order_link(order: Order) -> str:
  return f'{request.headers.get("Origin")}/order/{hashids.encode(order.id)}'


def get_delivery_groups(schedule: Schedule) -> list[DeliveryGroup]:
  with Session() as session:
    return session.query(DeliveryGroup).filter(DeliveryGroup.schedule_id == schedule.id).all()

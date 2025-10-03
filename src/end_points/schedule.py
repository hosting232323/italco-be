import os
from hashids import Hashids
from sqlalchemy import and_
from datetime import datetime
from flask import Blueprint, request

from .. import IS_DEV
from api.sms import send_sms
from database_api import Session
from . import flask_session_authentication
from ..database.enum import UserRole, OrderStatus
from database_api.operations import create, delete, get_by_id, update, get_by_ids
from ..database.schema import Schedule, ItalcoUser, Order, DeliveryGroup, Transport, ServiceUser, OrderServiceUser


schedule_bp = Blueprint('schedule_bp', __name__)
hashids = Hashids(salt='mia-chiave-segreta-super-segreta', min_length=8)


@schedule_bp.route('', methods=['POST'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN])
def create_schedule(user: ItalcoUser):
  orders, orders_data_map, schedule_data, response = format_schedule_data(request.json)
  if response:
    return response

  schedule = create(Schedule, schedule_data)
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
def delete_schedule(user: ItalcoUser, id):
  schedule = get_by_id(Schedule, int(id))
  orders = get_related_orders(schedule)
  delete(schedule)
  for order in orders:
    remove_order_from_schedule(order)
  return {'status': 'ok', 'message': 'Operazione completata'}


@schedule_bp.route('', methods=['GET'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN])
def get_schedules(user: ItalcoUser):
  schedules = []
  for tupla in query_schedules():
    schedules = format_query_result(tupla, schedules)
  return {'status': 'ok', 'schedules': schedules}


@schedule_bp.route('<id>', methods=['PUT'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN])
def update_schedule(user: ItalcoUser, id):
  if 'deleted_orders' in request.json:
    for order in get_by_ids(Order, request.json['deleted_orders']):
      remove_order_from_schedule(order)
    del request.json['deleted_orders']
  orders, orders_data_map, schedule_data, response = format_schedule_data(request.json, id)
  if response:
    return response

  schedule: Schedule = update(get_by_id(Schedule, int(id)), schedule_data)
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


def query_schedules() -> list[tuple[Schedule, DeliveryGroup, Transport, Order]]:
  with Session() as session:
    return (
      session.query(Schedule, DeliveryGroup, Transport, Order)
      .join(DeliveryGroup, Schedule.delivery_group_id == DeliveryGroup.id)
      .join(Transport, Schedule.transport_id == Transport.id)
      .outerjoin(Order, Order.schedule_id == Schedule.id)
      .all()
    )


def query_schedules_count(delivery_group_id, schedule_date, this_id) -> int:
  with Session() as session:
    return (
      session.query(Schedule)
      .filter(
        Schedule.delivery_group_id == delivery_group_id,
        Schedule.date == datetime.strptime(schedule_date, '%Y-%m-%d').date(),
        Schedule.id != this_id,
      )
      .count()
    )


def get_related_orders(schedule: Schedule) -> list[Order]:
  with Session() as session:
    return session.query(Order).filter(Order.schedule_id == schedule.id).all()


def format_query_result(tupla: tuple[Schedule, DeliveryGroup, Transport, Order], list: list[dict]) -> list[dict]:
  for element in list:
    if element['id'] == tupla[0].id:
      element['orders'].append(tupla[3].to_dict())
      return list

  list.append(
    {
      **tupla[0].to_dict(),
      'orders': [tupla[3].to_dict()],
      'transport': tupla[2].to_dict(),
      'delivery_group': tupla[1].to_dict(),
    }
  )
  return list


def get_selling_point(order: Order) -> str:
  with Session() as session:
    return (
      session.query(ItalcoUser.email)
      .join(ServiceUser, ItalcoUser.id == ServiceUser.user_id)
      .join(
        OrderServiceUser,
        and_(ServiceUser.id == OrderServiceUser.service_user_id, OrderServiceUser.order_id == order.id),
      )
      .scalar()
    )


def remove_order_from_schedule(order: Order):
  update(order, {'schedule_id': None, 'assignament_date': None, 'status': OrderStatus.PENDING})


def format_schedule_data(schedule_data: dict, schedule_id: int = None):
  orders_data = schedule_data['orders']
  del schedule_data['orders']
  if 'order_ids' in schedule_data:
    del schedule_data['order_ids']
  if 'deleted_orders' in schedule_data:
    del schedule_data['deleted_orders']
  if 'delivery_group' in schedule_data:
    del schedule_data['delivery_group']
  if 'transport' in schedule_data:
    del schedule_data['transport']
  orders: list[Order] = get_by_ids(Order, [o['id'] for o in orders_data])
  if not orders:
    return None, None, None, {'status': 'ko', 'error': 'Errore nella creazione del borderò'}

  if query_schedules_count(schedule_data['delivery_group_id'], schedule_data['date'], schedule_id) > 0:
    return None, None, None, {'status': 'ko', 'error': 'Esiste già un borderò per questa data'}

  orders_data_map = {o['id']: o for o in orders_data}
  return orders, orders_data_map, schedule_data, None


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

import os
from hashids import Hashids
from sqlalchemy import and_
from datetime import datetime
from flask import Blueprint, request

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
  order_ids = [o['id'] for o in request.json['orders']]
  orders_data = request.json['orders']

  del request.json['order_ids']
  del request.json['orders']
  orders: list[Order] = get_by_ids(Order, order_ids)
  if not orders:
    return {'status': 'ko', 'error': 'Errore nella creazione del borderò'}

  if query_schedules_count(request.json['delivery_group_id'], request.json['date']) > 0:
    return {'status': 'ko', 'error': 'Esiste già un borderò per questa data'}

  schedule = create(Schedule, request.json)
  orders_data_map = {o['id']: o for o in orders_data}
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

      if order.addressee_contact:
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

  return {'status': 'ok', 'schedule': schedule.to_dict()}


@schedule_bp.route('<id>', methods=['DELETE'])
@flask_session_authentication([UserRole.ADMIN])
def delete_schedule(user: ItalcoUser, id):
  schedule = get_by_id(Schedule, int(id))
  orders = get_related_orders(schedule)
  delete(schedule)
  for order in orders:
    update(order, {'schedule_id': None, 'assignament_date': None, 'status': OrderStatus.PENDING})
  return {'status': 'ok', 'message': 'Operazione completata'}


@schedule_bp.route('', methods=['GET'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN])
def get_schedules(user: ItalcoUser):
  schedules = []
  for tupla in query_schedules():
    schedules = format_query_result(tupla, schedules)
  return {'status': 'ok', 'schedules': schedules}


@schedule_bp.route('<id>', methods=['PUT'])
@flask_session_authentication([UserRole.ADMIN])
def update_schedule(user: ItalcoUser, id):
  schedule: Schedule = get_by_id(Schedule, int(id))
  return {'status': 'ok', 'order': update(schedule, request.json).to_dict()}


def query_schedules() -> list[tuple[Schedule, DeliveryGroup, Transport, Order]]:
  with Session() as session:
    return (
      session.query(Schedule, DeliveryGroup, Transport, Order)
      .join(DeliveryGroup, Schedule.delivery_group_id == DeliveryGroup.id)
      .join(Transport, Schedule.transport_id == Transport.id)
      .outerjoin(Order, Order.schedule_id == Schedule.id)
      .all()
    )


def query_schedules_count(delivery_group_id, schedule_date) -> int:
  with Session() as session:
    return (
      session.query(Schedule)
      .filter(
        Schedule.delivery_group_id == delivery_group_id,
        Schedule.date == datetime.strptime(schedule_date, '%Y-%m-%d').date(),
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


def get_order_link(order: Order) -> str:
  return f'{request.headers.get("Origin")}/order/{hashids.encode(order.id)}'

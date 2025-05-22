from datetime import datetime
from flask import Blueprint, request

from database_api import Session
from ..database.enum import UserRole, OrderStatus
from . import error_catching_decorator, flask_session_authentication
from database_api.operations import create, delete, get_by_id, update, get_by_ids
from ..database.schema import Schedule, ItalcoUser, Order, DeliveryGroup, Transport


schedule_bp = Blueprint('schedule_bp', __name__)


@schedule_bp.route('', methods=['POST'])
@error_catching_decorator
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN])
def create_schedule(user: ItalcoUser):
  orders: list[Order] = get_by_ids(Order, request.json['order_ids'])
  del request.json['order_ids']
  schedule = create(Schedule, request.json)
  if not schedule or not orders:
    return {
      'status': 'ko',
      'error': 'Errore nella creazione del borderò'
    }

  for order in orders:
    update(order, {
      'schedule_id': schedule.id,
      'status': OrderStatus.IN_PROGRESS,
      'assignament_date': datetime.now()
    })
  return {
    'status': 'ok',
    'schedule': schedule.to_dict()
  }


@schedule_bp.route('<id>', methods=['DELETE'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN])
def delete_schedule(user: ItalcoUser, id):
  schedule = get_by_id(Schedule, int(id))
  orders = get_related_orders(schedule)
  delete(schedule)
  for order in orders:
    update(order, {
      'schedule_id': None,
      'assignament_date': None,
      'status': OrderStatus.PENDING
    })
  return {
    'status': 'ok',
    'message': 'Operazione completata'
  }


@schedule_bp.route('', methods=['GET'])
@error_catching_decorator
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN])
def get_schedules(user: ItalcoUser):
  schedules = []
  for tupla in query_schedules():
    schedules = format_query_result(tupla, schedules)
  return {
    'status': 'ok',
    'schedules': schedules
  }


@schedule_bp.route('<id>', methods=['PUT'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN])
def update_schedule(user: ItalcoUser, id):
  schedule: Schedule = get_by_id(Schedule, int(id))
  return {
    'status': 'ok',
    'order': update(schedule, request.json).to_dict()
  }


def query_schedules() -> list[tuple[Schedule, DeliveryGroup, Transport, Order]]:
  with Session() as session:
    return session.query(
      Schedule, DeliveryGroup, Transport, Order
    ).join(
      DeliveryGroup, Schedule.delivery_group_id == DeliveryGroup.id
    ).join(
      Transport, Schedule.transport_id == Transport.id
    ).outerjoin(
      Order, Order.schedule_id == Schedule.id
    ).all()


def get_related_orders(schedule: Schedule) -> list[Order]:
  with Session() as session:
    return session.query(Order).filter(
      Order.schedule_id == schedule.id
    ).all()


def format_query_result(tupla: tuple[
  Schedule, DeliveryGroup, Transport, Order
], list: list[dict]) -> list[dict]:
  for element in list:
    if element['id'] == tupla[0].id:
      element['orders'].append(tupla[3].to_dict())
      return list

  list.append({
    **tupla[0].to_dict(),
    'orders': [tupla[3].to_dict()],
    'transport': tupla[2].to_dict(),
    'delivery_group': tupla[1].to_dict()
  })
  return list

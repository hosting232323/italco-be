from datetime import datetime
from flask import Blueprint, request

from database_api import Session
from ...database.enum import UserRole
from ...schedulation import execute_schedulation
from .. import flask_session_authentication
from ...schedulation.building import build_schedule_items
from ...database.schema import Schedule, User, DeliveryGroup
from .delivery import get_items_for_delivery, get_history_for_delivery, update_schedule_item
from .position import get_schedule_position, claim_schedule_position
from .sms_sender import schedule_sms_check
from database_api.operations import create, delete, get_by_id, update
from ..orders.queries import query_orders, format_query_result as format_query_orders_result
from .utils import (
  handle_schedule_item,
  delete_schedule_items,
  schedule_items_updating,
  format_schedule_data,
  save_info_to_euronics,
)
from .queries import (
  query_schedules,
  query_schedules_count,
  lock_delivery_assignment,
  query_invalid_delivery_user_ids,
  format_query_result,
  get_delivery_groups,
  get_schedule_items,
  get_schedule_item_users,
  get_schedule_item_for_order_id_filter,
  format_schedule_item,
)


schedule_bp = Blueprint('schedule_bp', __name__)


@schedule_bp.route('', methods=['POST'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN])
def create_schedule(user: User):
  with Session() as session:
    schedule_items, schedule_data, users, response = format_schedule_data(request.json, session=session)
    if response:
      return response

    user_ids = sorted({delivery_user['id'] for delivery_user in users})
    if query_invalid_delivery_user_ids(user_ids, session=session):
      return {'status': 'ko', 'message': 'Uno o più utenti selezionati non sono utenti delivery validi'}

    for user_id in user_ids:
      lock_delivery_assignment(user_id, schedule_data['date'], session=session)
    if any(query_schedules_count(user_id, schedule_data['date'], session=session) > 0 for user_id in user_ids):
      return {'status': 'ko', 'message': 'Uno di questi utenti delivery è già assegnato'}

    schedule: Schedule = create(Schedule, schedule_data, session=session)
    for user_id in user_ids:
      create(DeliveryGroup, {'schedule_id': schedule.id, 'user_id': user_id}, session=session)
    pending_sms = []
    for item in schedule_items:
      handle_schedule_item(item, schedule, session, pending_sms=pending_sms)

    session.commit()
    save_info_to_euronics(schedule_items)
    for sms_order, sms_item in pending_sms:
      schedule_sms_check(sms_order, sms_item)
  return {'status': 'ok', 'schedule': schedule.to_dict()}


@schedule_bp.route('<id>', methods=['DELETE'])
@flask_session_authentication([UserRole.ADMIN])
def delete_schedule(_, id):
  with Session() as session:
    schedule: Schedule = get_by_id(Schedule, int(id), session=session)
    for delivery_group in get_delivery_groups(schedule, session=session):
      delete(delivery_group, session=session)
    for schedule_item_user in get_schedule_item_users(schedule, session=session):
      delete(schedule_item_user, session=session)
    delete_schedule_items(get_schedule_items(schedule, session=session), session=session)
    delete(schedule, session=session)

    session.commit()
  return {'status': 'ok', 'message': 'Operazione completata'}


@schedule_bp.route('filter', methods=['POST'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN, UserRole.DELIVERY])
def get_schedules(_):
  schedules = []
  for tupla in query_schedules(request.json['filters'], 100):
    schedules = format_query_result(tupla, schedules)

  if any(filter['model'] == 'Order' and filter['field'] == 'id' for filter in request.json['filters']):
    for schedule in schedules:
      for tupla in get_schedule_item_for_order_id_filter(schedule['id']):
        format_schedule_item(schedule['schedule_items'], tupla[1], tupla[2], tupla[3], tupla[4], None)

  return {'status': 'ok', 'schedules': schedules}


@schedule_bp.route('<id>', methods=['PUT'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN])
def update_schedule(user: User, id):
  with Session() as session:
    schedule: Schedule = get_by_id(Schedule, int(id), session=session)
    actual_schedule_items = get_schedule_items(schedule, session=session)
    delivery_groups = get_delivery_groups(schedule, session=session)
    deleted_users = request.json.get('deleted_users', [])
    for user_id in deleted_users:
      for delivery_group in delivery_groups:
        if delivery_group.user_id == user_id:
          delete(delivery_group, session=session)
          break

    schedule_items, schedule_data, users, response = format_schedule_data(request.json, session=session)
    if response:
      session.rollback()
      return response

    payload_user_ids = sorted({delivery_user['id'] for delivery_user in users})
    if query_invalid_delivery_user_ids(payload_user_ids, session=session):
      session.rollback()
      return {'status': 'ko', 'message': 'Uno o più utenti selezionati non sono utenti delivery validi'}

    schedule = update(schedule, schedule_data, session=session)
    actual_user_ids = list(set([delivery_group.user_id for delivery_group in delivery_groups]) - set(deleted_users))
    # Lo stato finale include anche gli utenti già associati e non cancellati,
    # pur se omessi dal payload: restano nel DB e vanno verificati anch'essi.
    final_user_ids = sorted(set(payload_user_ids) | set(actual_user_ids))
    for user_id in final_user_ids:
      lock_delivery_assignment(user_id, schedule.date, session=session)
    for user_id in final_user_ids:
      if query_schedules_count(user_id, schedule.date, exclude_schedule_id=schedule.id, session=session) > 0:
        session.rollback()
        return {'status': 'ko', 'message': 'Uno di questi utenti delivery è già assegnato'}
      if user_id not in actual_user_ids:
        create(DeliveryGroup, {'schedule_id': schedule.id, 'user_id': user_id}, session=session)

    pending_sms = []
    schedule_items_updating(schedule_items, actual_schedule_items, schedule, session=session, pending_sms=pending_sms)
    session.commit()
    save_info_to_euronics(schedule_items)
    for sms_order, sms_item in pending_sms:
      schedule_sms_check(sms_order, sms_item)
  return {'status': 'ok', 'schedule': schedule.to_dict()}


@schedule_bp.route('suggestions', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN])
def get_schedule_suggestions(user: User):
  return execute_schedulation(
    user,
    datetime.strptime(request.args['work_date'], '%Y-%m-%d'),
    int(request.args['min_size_group']),
    int(request.args['max_size_group']),
    int(request.args['max_distance_km']),
  )


@schedule_bp.route('pianification', methods=['POST'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN])
def pianification(_):
  orders = []
  for tupla in query_orders([{'model': 'Order', 'field': 'id', 'value': request.json['orders_id']}]):
    orders = format_query_orders_result(tupla, orders)
  if len(orders) == 0:
    return {'status': 'ko', 'message': 'Ordini non identificati'}

  for order in orders:
    if order['status'] != 'Booked':
      return {'status': 'ko', 'message': 'Hai selezionato degli ordini che non sono in stato Booked'}

  return {'status': 'ok', 'schedule_items': build_schedule_items(orders)}


@schedule_bp.route('item/<id>', methods=['PUT'])
@flask_session_authentication([UserRole.DELIVERY])
def update_schedule_item_endpoint(user: User, id):
  return update_schedule_item(user, int(id), request.json['completed'])


@schedule_bp.route('history', methods=['GET'])
@flask_session_authentication([UserRole.DELIVERY])
def get_history_for_delivery_endpoint(user: User):
  return get_history_for_delivery(user)


@schedule_bp.route('delivery', methods=['GET'])
@flask_session_authentication([UserRole.DELIVERY])
def get_items_for_delivery_endpoint(user: User):
  return get_items_for_delivery(user)


@schedule_bp.route('<id>/position', methods=['GET'])
@flask_session_authentication([UserRole.DELIVERY])
def get_schedule_position_endpoint(user: User, id):
  return get_schedule_position(user, int(id))


@schedule_bp.route('<id>/position', methods=['POST'])
@flask_session_authentication([UserRole.DELIVERY])
def claim_schedule_position_endpoint(user: User, id):
  return claim_schedule_position(user, int(id))

"""Storico borderò del corriere: /schedule/history restituisce i borderò dei
giorni precedenti (non quello di oggi), ordinati per data decrescente."""

from datetime import date, time, timedelta

import database_api
from database_api.operations import create
from src.database.enum import OrderStatus, OrderType, ScheduleType, UserRole
from src.database.schema import (
  DeliveryGroup,
  Order,
  Schedule,
  ScheduleItem,
  ScheduleItemOrder,
  Transport,
  User,
)
from src.end_points.schedule.delivery import get_history_for_delivery


def _schedule_with_order(session, user, transport, schedule_date, addressee):
  schedule = create(Schedule, {'date': schedule_date, 'transport_id': transport.id}, session=session)
  create(DeliveryGroup, {'schedule_id': schedule.id, 'user_id': user.id}, session=session)
  order = create(
    Order,
    {
      'addressee': addressee,
      'address': 'Via Bari 1',
      'cap': '70100',
      'dpc': '2026-07-14',
      'drc': '2026-07-14',
      'status': OrderStatus.DELIVERED,
      'type': OrderType.DELIVERY,
    },
    session=session,
  )
  item = create(
    ScheduleItem,
    {
      'index': 0,
      'schedule_id': schedule.id,
      'operation_type': ScheduleType.ORDER,
      'start_time_slot': time(8, 0),
      'end_time_slot': time(9, 0),
    },
    session=session,
  )
  create(ScheduleItemOrder, {'order_id': order.id, 'schedule_item_id': item.id}, session=session)
  return schedule


def test_history_returns_past_borderos_desc(seeded_db):
  today = date.today()
  with database_api.Session() as session:
    user = create(User, {'email': 'Elmy', 'password': 'x', 'role': UserRole.DELIVERY}, session=session)
    transport = create(Transport, {'name': 'Furgone 1', 'plate': 'AA000AA', 'cap': '70100'}, session=session)
    _schedule_with_order(session, user, transport, today, 'Oggi')
    _schedule_with_order(session, user, transport, today - timedelta(days=1), 'Ieri')
    _schedule_with_order(session, user, transport, today - timedelta(days=3), 'TreGiorniFa')
    session.commit()
    user_id = user.id

  with database_api.Session() as session:
    user = session.query(User).filter(User.id == user_id).first()
    response = get_history_for_delivery(user)

  assert response['status'] == 'ok'
  dates = [s['date'] for s in response['schedules']]
  # solo i giorni precedenti, in ordine decrescente; niente oggi
  assert dates == sorted(dates, reverse=True)
  assert (today - timedelta(days=1)).isoformat() in dates
  assert (today - timedelta(days=3)).isoformat() in dates
  assert today.isoformat() not in dates


def test_history_empty_for_new_courier(seeded_db):
  with database_api.Session() as session:
    user = create(User, {'email': 'Nuovo', 'password': 'x', 'role': UserRole.DELIVERY}, session=session)
    session.commit()
    user_id = user.id

  with database_api.Session() as session:
    user = session.query(User).filter(User.id == user_id).first()
    response = get_history_for_delivery(user)

  assert response == {'status': 'ok', 'schedules': []}

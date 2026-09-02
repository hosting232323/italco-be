"""Chiusura ordine da corriere: il payload rimanda in eco tutto lo schedule
item (inclusi created_at/updated_at in formato DD/MM/YYYY) e non deve rompere
l'UPDATE dell'ordine."""

from datetime import date, time

import database_api
from database_api.operations import create
from src.database.enum import OrderStatus, OrderType, ScheduleType, UserRole
from src.database.schema import (
  CollectionPoint,
  DeliveryGroup,
  Order,
  Product,
  Schedule,
  ScheduleItem,
  ScheduleItemOrder,
  Service,
  ServiceUser,
  Transport,
  User,
)
from src.end_points.orders.crud import update_order


def _seed_order_for_delivery(session):
  user = create(User, {'email': 'Elmy', 'password': 'x', 'role': UserRole.DELIVERY}, session=session)
  owner = create(User, {'email': 'cust', 'password': 'x', 'role': UserRole.CUSTOMER}, session=session)
  transport = create(Transport, {'name': 'Furgone 1', 'plate': 'AA000AA', 'cap': '70100'}, session=session)
  schedule = create(Schedule, {'date': date.today(), 'transport_id': transport.id}, session=session)
  create(DeliveryGroup, {'schedule_id': schedule.id, 'user_id': user.id}, session=session)
  cp = create(
    CollectionPoint,
    {'name': 'PV 20', 'address': 'Via X', 'cap': '70100', 'user_id': owner.id},
    session=session,
  )
  order = create(
    Order,
    {
      'addressee': 'Mario Rossi',
      'address': 'Via Bari 1',
      'cap': '70100',
      'dpc': '2026-07-14',
      'drc': '2026-07-14',
      'status': OrderStatus.BOOKING,
      'type': OrderType.DELIVERY,
    },
    session=session,
  )
  service = create(
    Service,
    {'name': 'Reso al piano', 'type': OrderType.DELIVERY, 'duration': 30, 'max_services': 3, 'professional': False},
    session=session,
  )
  service_user = create(
    ServiceUser,
    {'code': 'SVC-1', 'price': 10.0, 'user_id': user.id, 'service_id': service.id},
    session=session,
  )
  create(
    Product,
    {'name': 'BOSCH', 'order_id': order.id, 'collection_point_id': cp.id, 'service_user_id': service_user.id},
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
  session.commit()
  return user.id, order.id, cp.id


def _echoed_payload(order_id: int, cp_id: int, release_collection_point_id: int) -> dict:
  """Payload come lo costruisce l'app: rawPayload dello schedule item con i
  timestamp serializzati DD/MM/YYYY e l'override dello stato."""
  return {
    'id': order_id,
    'order_id': order_id,
    'operation_type': 'Order',
    'index': 0,
    'address': 'Via Bari 1',
    'cap': '70100',
    'addressee': 'Mario Rossi',
    'dpc': '2026-07-14',
    'drc': '2026-07-14',
    'start_time_slot': '08:00:00',
    'end_time_slot': '09:00:00',
    'created_at': '14/07/2026 08:25',
    'updated_at': '14/07/2026 14:34',
    'version': 4,
    'status': 'To Reschedule',
    'type': 'Delivery',
    'completed': False,
    'products': {
      'BOSCH': {
        'collection_point': {'id': cp_id},
        'release_collection_point_id': release_collection_point_id,
      },
    },
  }


def test_reschedule_to_vehicle_with_echoed_timestamps(seeded_db):
  with database_api.Session() as session:
    user_id, order_id, cp_id = _seed_order_for_delivery(session)

  payload = _echoed_payload(order_id, cp_id, release_collection_point_id=0)

  with database_api.Session() as session:
    order = session.query(Order).filter(Order.id == order_id).first()
    user = session.query(User).filter(User.id == user_id).first()
    update_order(user, order, payload, session)
    session.commit()

  with database_api.Session() as session:
    order = session.query(Order).filter(Order.id == order_id).first()
    product = session.query(Product).filter(Product.order_id == order_id).first()
    assert order.status == OrderStatus.TO_RESCHEDULE
    # Veicolo (id 0) -> il prodotto viene rilasciato sul mezzo del corriere.
    assert product.release_transport_id is not None
    assert product.release_collection_point_id is None


def test_reschedule_to_collection_point_with_echoed_timestamps(seeded_db):
  with database_api.Session() as session:
    user_id, order_id, cp_id = _seed_order_for_delivery(session)

  payload = _echoed_payload(order_id, cp_id, release_collection_point_id=cp_id)

  with database_api.Session() as session:
    order = session.query(Order).filter(Order.id == order_id).first()
    user = session.query(User).filter(User.id == user_id).first()
    update_order(user, order, payload, session)
    session.commit()

  with database_api.Session() as session:
    order = session.query(Order).filter(Order.id == order_id).first()
    product = session.query(Product).filter(Product.order_id == order_id).first()
    assert order.status == OrderStatus.TO_RESCHEDULE
    assert product.release_collection_point_id == cp_id

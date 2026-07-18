from datetime import time

from database_api import Session
from database_api.operations import get_by_id

from src.database.enum import OrderStatus, RaeStatus
from src.database.schema import (
  Order,
  RaeProduct,
  ScheduleItem,
  ScheduleItemCollectionPoint,
  ScheduleItemOrder,
)
from src.end_points.schedule.utils import (
  delete_schedule_items,
  format_schedule_data,
  handle_schedule_item,
  save_info_to_euronics,
  schedule_items_updating,
)
from src.end_points.schedule.queries import get_schedule_items

from tests.unit.factories import (
  create_collection_point,
  create_order,
  create_product,
  create_rae_product,
  create_schedule,
  create_user,
  customer_with_service,
  link_order_to_schedule,
)
from src.database.enum import UserRole


def test_format_schedule_data_resolves_orders_and_collection_points(db):
  customer = create_user(UserRole.CUSTOMER)
  order = create_order()
  collection_point = create_collection_point(customer)
  payload = {
    'date': '2026-07-15',
    'transport_id': 1,
    'users': [{'id': 5}],
    'schedule_items': [
      {
        'index': 0,
        'operation_type': 'Order',
        'order_id': order.id,
        'start_time_slot': '08:00',
        'end_time_slot': '10:00',
      },
      {
        'index': 1,
        'operation_type': 'CollectionPoint',
        'collection_point_id': collection_point.id,
        'start_time_slot': '10:00',
        'end_time_slot': '11:00',
      },
    ],
  }

  with Session() as session:
    schedule_items, schedule_data, users, response = format_schedule_data(payload, session=session)

  assert response is None
  assert users == [{'id': 5}]
  assert schedule_data == {'date': '2026-07-15', 'transport_id': 1}
  assert schedule_items[0]['order'].id == order.id
  assert schedule_items[1]['collection_point'].id == collection_point.id


def test_format_schedule_data_fails_without_orders(db):
  payload = {'date': '2026-07-15', 'users': [{'id': 5}], 'schedule_items': []}

  with Session() as session:
    schedule_items, schedule_data, users, response = format_schedule_data(payload, session=session)

  assert response == {'status': 'ko', 'message': 'Errore nella creazione del borderò'}
  assert schedule_items is None


def test_format_schedule_data_fails_without_users(db):
  order = create_order()
  payload = {
    'date': '2026-07-15',
    'users': [],
    'schedule_items': [
      {
        'index': 0,
        'operation_type': 'Order',
        'order_id': order.id,
        'start_time_slot': '08:00',
        'end_time_slot': '10:00',
      }
    ],
  }

  with Session() as session:
    _, _, _, response = format_schedule_data(payload, session=session)

  assert response is not None


def test_handle_schedule_item_order_emits_rae_and_updates_status(db):
  customer, _, service_user, _ = customer_with_service()
  order = create_order(status=OrderStatus.BOOKED)
  rae_product = create_rae_product(order, customer)
  create_product(order, service_user, rae_product_id=rae_product.id)
  schedule = create_schedule()

  with Session() as session:
    order_in_session = session.get(Order, order.id)
    handle_schedule_item(
      {
        'index': 0,
        'operation_type': 'Order',
        'order': order_in_session,
        'start_time_slot': '08:00',
        'end_time_slot': '10:00',
      },
      schedule,
      session,
      pending_sms=[],
    )
    session.commit()

  assert get_by_id(Order, order.id).status == OrderStatus.SCHEDULED
  refreshed_rae = get_by_id(RaeProduct, rae_product.id)
  assert refreshed_rae.status == RaeStatus.EMITTED
  assert refreshed_rae.dtr_date == schedule.date
  with Session() as session:
    assert session.query(ScheduleItemOrder).count() == 1


def test_handle_schedule_item_collection_point(db):
  customer = create_user(UserRole.CUSTOMER)
  collection_point = create_collection_point(customer)
  schedule = create_schedule()

  with Session() as session:
    handle_schedule_item(
      {
        'index': 0,
        'operation_type': 'CollectionPoint',
        'collection_point': collection_point,
        'start_time_slot': '08:00',
        'end_time_slot': '10:00',
      },
      schedule,
      session,
      pending_sms=[],
    )
    session.commit()

  with Session() as session:
    link = session.query(ScheduleItemCollectionPoint).one()
    assert link.collection_point_id == collection_point.id


def test_delete_schedule_items_restores_orders_and_rae(db):
  customer, _, service_user, _ = customer_with_service()
  order = create_order(status=OrderStatus.SCHEDULED)
  rae_product = create_rae_product(order, customer, status=RaeStatus.EMITTED)
  create_product(order, service_user, rae_product_id=rae_product.id)
  schedule = create_schedule()
  link_order_to_schedule(order, schedule)

  with Session() as session:
    delete_schedule_items(get_schedule_items(schedule, session=session), session=session)
    session.commit()

  assert get_by_id(Order, order.id).status == OrderStatus.BOOKED
  assert get_by_id(RaeProduct, rae_product.id).status == RaeStatus.ANNULLED
  with Session() as session:
    assert session.query(ScheduleItem).count() == 0
    assert session.query(ScheduleItemOrder).count() == 0


def test_schedule_items_updating_updates_creates_and_deletes(db):
  _, _, service_user, _ = customer_with_service()
  schedule = create_schedule()

  kept_order = create_order(status=OrderStatus.SCHEDULED)
  create_product(kept_order, service_user)
  kept_item = link_order_to_schedule(kept_order, schedule, index=0)

  removed_order = create_order(status=OrderStatus.SCHEDULED)
  create_product(removed_order, service_user)
  link_order_to_schedule(removed_order, schedule, index=1)

  new_order = create_order(status=OrderStatus.BOOKED)
  create_product(new_order, service_user)

  with Session() as session:
    actual_items = get_schedule_items(schedule, session=session)
    new_order_in_session = session.get(Order, new_order.id)
    schedule_items_updating(
      [
        {
          'id': kept_item.id,
          'index': 5,
          'start_time_slot': '12:00',
          'end_time_slot': '14:00',
        },
        {
          'index': 1,
          'operation_type': 'Order',
          'order': new_order_in_session,
          'start_time_slot': '08:00',
          'end_time_slot': '10:00',
        },
      ],
      actual_items,
      schedule,
      session=session,
      pending_sms=[],
    )
    session.commit()

  refreshed_kept = get_by_id(ScheduleItem, kept_item.id)
  assert refreshed_kept.index == 5
  assert refreshed_kept.start_time_slot == time(12, 0)
  assert get_by_id(Order, removed_order.id).status == OrderStatus.BOOKED
  assert get_by_id(Order, new_order.id).status == OrderStatus.SCHEDULED
  with Session() as session:
    assert session.query(ScheduleItemOrder).count() == 2


def test_save_info_to_euronics_forwards_orders(db, monkeypatch):
  import src.end_points.schedule.utils as schedule_utils

  forwarded = []
  monkeypatch.setattr(schedule_utils, 'save_order_status_to_euronics', lambda order: forwarded.append(order))
  order = create_order()

  save_info_to_euronics(
    [
      {'operation_type': 'Order', 'order': order},
      {'operation_type': 'CollectionPoint', 'collection_point': None},
    ]
  )

  assert forwarded == [order]

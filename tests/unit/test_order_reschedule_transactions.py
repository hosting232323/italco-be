from datetime import date, time

from database_api import Session
from database_api.operations import create

from src.database.enum import ScheduleType
from src.database.schema import (
  CollectionPoint,
  Order,
  Product,
  Schedule,
  ScheduleItem,
  ScheduleItemOrder,
  ServiceUser,
  Transport,
)
from src.database.enum import UserRole
from src.database.schema import DeliveryGroup
from src.end_points.orders.clone import reschedule_products
from src.end_points.schedule.queries import get_schedule_item_by_order
from tests.unit.factories import create_user


def test_reschedule_sees_products_pending_in_the_current_session(seeded_db):
  product_name = 'pending-reschedule-product'
  with Session() as session:
    order = session.query(Order).first()
    service_user_id = session.query(ServiceUser.id).first()[0]
    release_collection_point_id = session.query(CollectionPoint.id).first()[0]
    product = create(
      Product,
      {
        'name': product_name,
        'order_id': order.id,
        'service_user_id': service_user_id,
      },
      session=session,
    )

    reschedule_products(
      1,
      order,
      {product_name: {'release_collection_point_id': release_collection_point_id}},
      session,
    )
    product_id = product.id
    session.commit()

  with Session() as session:
    reloaded = session.query(Product).filter(Product.id == product_id).one()
    assert reloaded.release_collection_point_id == release_collection_point_id


def test_reschedule_to_transport_uses_delivery_transport_in_session(seeded_db):
  product_name = 'reschedule-to-transport'
  delivery = create_user(UserRole.DELIVERY)
  with Session() as session:
    order = session.query(Order).first()
    service_user_id = session.query(ServiceUser.id).first()[0]
    transport = session.query(Transport).first()
    schedule = create(Schedule, {'date': date.today(), 'transport_id': transport.id}, session=session)
    create(DeliveryGroup, {'schedule_id': schedule.id, 'user_id': delivery.id}, session=session)
    product = create(
      Product,
      {'name': product_name, 'order_id': order.id, 'service_user_id': service_user_id},
      session=session,
    )

    reschedule_products(delivery.id, order, {product_name: {'release_collection_point_id': 0}}, session)
    product_id = product.id
    transport_id = transport.id
    session.commit()

  with Session() as session:
    reloaded = session.query(Product).filter(Product.id == product_id).one()
    assert reloaded.release_transport_id == transport_id


def test_reschedule_without_delivery_transport_leaves_product_unchanged(seeded_db):
  product_name = 'reschedule-no-transport'
  lonely_delivery = create_user(UserRole.DELIVERY)
  with Session() as session:
    order = session.query(Order).first()
    service_user_id = session.query(ServiceUser.id).first()[0]
    product = create(
      Product,
      {'name': product_name, 'order_id': order.id, 'service_user_id': service_user_id},
      session=session,
    )

    reschedule_products(lonely_delivery.id, order, {product_name: {'release_collection_point_id': 0}}, session)
    product_id = product.id
    session.commit()

  with Session() as session:
    reloaded = session.query(Product).filter(Product.id == product_id).one()
    assert reloaded.release_transport_id is None


def test_get_schedule_item_by_order_sees_pending_items_in_session(seeded_db):
  with Session() as session:
    order = session.query(Order).filter(~Order.schedule_item_order.any()).first()
    transport = session.query(Transport).first()
    schedule = create(Schedule, {'date': date.today(), 'transport_id': transport.id}, session=session)
    item = create(
      ScheduleItem,
      {
        'index': 0,
        'start_time_slot': time(8),
        'end_time_slot': time(10),
        'operation_type': ScheduleType.ORDER,
        'schedule_id': schedule.id,
      },
      session=session,
    )
    create(ScheduleItemOrder, {'order_id': order.id, 'schedule_item_id': item.id}, session=session)

    found = get_schedule_item_by_order(order, session=session)
    assert found is not None
    assert found.id == item.id
    order_id = order.id
    session.rollback()

  with Session() as session:
    reloaded_order = session.query(Order).filter(Order.id == order_id).one()
    assert get_schedule_item_by_order(reloaded_order, session=session) is None

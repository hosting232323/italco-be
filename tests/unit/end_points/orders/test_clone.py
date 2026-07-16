from database_api import Session
from database_api.operations import get_by_id

from src.database.enum import OrderStatus, UserRole
from src.database.schema import Order, Product
from src.end_points.orders.clone import (
  format_data_cloning_order,
  format_data_cloning_product,
  reschedule_products,
  update_cloned_order,
)

from tests.unit.factories import (
  create_delivery_group,
  create_order,
  create_product,
  create_schedule,
  create_transport,
  create_user,
  customer_with_service,
)


def test_format_data_cloning_order_adds_note():
  data = format_data_cloning_order({}, 42)

  assert data['operator_note'] == 'Clonato da ordine 42'


def test_format_data_cloning_order_preserves_existing_note():
  data = format_data_cloning_order({'operator_note': 'urgente'}, 42)

  assert data['operator_note'] == 'Clonato da ordine 42, urgente'


def test_format_data_cloning_product_prefers_collection_point():
  product_data = format_data_cloning_product({}, {'release_collection_point_id': 7})

  assert product_data['collection_point_id'] == 7


def test_format_data_cloning_product_falls_back_to_transport():
  product_data = format_data_cloning_product(
    {}, {'release_collection_point_id': None, 'release_transport_id': 9}
  )

  assert product_data['collection_point_id'] is None
  assert product_data['transport_id'] == 9


def test_format_data_cloning_product_no_release_info():
  product_data = format_data_cloning_product({'name': 'x'}, {})

  assert product_data == {'name': 'x'}


def test_update_cloned_order_marks_rescheduled(db):
  new_order = create_order()
  original = create_order(status=OrderStatus.TO_RESCHEDULE)

  with Session() as session:
    update_cloned_order(new_order, original.id, session=session)
    session.commit()

  refreshed = get_by_id(Order, original.id)
  assert refreshed.status == OrderStatus.RESCHEDULED
  assert refreshed.completion_date is not None
  assert refreshed.operator_note == f"Rischedulato con l'ordine {new_order.id}"


def test_update_cloned_order_appends_to_existing_note(db):
  new_order = create_order()
  original = create_order(operator_note='vecchia nota')

  with Session() as session:
    update_cloned_order(new_order, original.id, session=session)
    session.commit()

  assert get_by_id(Order, original.id).operator_note.endswith(', vecchia nota')


def test_reschedule_products_with_collection_point(db):
  customer, _, service_user, collection_point = customer_with_service()
  order = create_order()
  product = create_product(order, service_user, name='Frigo')

  with Session() as session:
    reschedule_products(
      1, order, {'Frigo': {'release_collection_point_id': collection_point.id}}, session=session
    )
    session.commit()

  assert get_by_id(Product, product.id).release_collection_point_id == collection_point.id


def test_reschedule_products_with_transport_fallback(db):
  _, _, service_user, _ = customer_with_service()
  order = create_order()
  product = create_product(order, service_user, name='Frigo')
  delivery = create_user(UserRole.DELIVERY)
  transport = create_transport()
  schedule = create_schedule(transport)
  create_delivery_group(delivery, schedule)

  with Session() as session:
    reschedule_products(delivery.id, order, {'Frigo': {'release_collection_point_id': 0}}, session=session)
    session.commit()

  assert get_by_id(Product, product.id).release_transport_id == transport.id

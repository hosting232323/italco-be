import pytest

from database_api import Session
from database_api.operations import get_by_id

from src.database.enum import OrderStatus, OrderType, ScheduleItemUserType, UserRole
from src.database.schema import Order, Product
from src.end_points.orders.crud import (
  create_order as crud_create_order,
  delete_order,
  filter_orders,
  get_order,
  update_order,
  update_order_customer,
)

from tests.unit.factories import (
  create_delivery_group,
  create_delivery_info,
  create_order,
  create_product,
  create_schedule,
  create_schedule_item_user,
  create_user,
  customer_with_service,
  link_order_to_schedule,
)


def _payload(service, collection_point, **extra):
  return {
    'type': 'Delivery',
    'addressee': 'Destinatario CRUD',
    'address': 'Via CRUD 1',
    'cap': '70121',
    'dpc': '2026-07-20',
    'drc': '2026-07-18',
    'products': {'Frigo': {'services': [{'id': service.id}], 'collection_point': {'id': collection_point.id}}},
    **extra,
  }


def test_create_order_builds_products(db):
  customer, service, service_user, collection_point = customer_with_service()

  result = crud_create_order(customer, _payload(service, collection_point))

  assert result['status'] == 'ok'
  with Session() as session:
    product = session.query(Product).one()
    assert product.service_user_id == service_user.id
    assert product.collection_point_id == collection_point.id
    assert product.name == 'Frigo'


def test_create_order_ignores_services_of_wrong_type(db):
  customer, service, _, collection_point = customer_with_service(order_type=OrderType.WITHDRAW)

  # L'ordine è di tipo Delivery ma il servizio è Withdraw: nessun prodotto creato
  result = crud_create_order(customer, _payload(service, collection_point))

  assert result['status'] == 'ok'
  with Session() as session:
    assert session.query(Product).count() == 0


def test_create_cloned_order_updates_original(db):
  customer, service, service_user, collection_point = customer_with_service()
  original = create_order(status=OrderStatus.TO_RESCHEDULE, operator_note='nota originale')
  create_product(original, service_user)

  payload = _payload(service, collection_point, cloned_order_id=original.id)
  payload['products']['Frigo']['release_collection_point_id'] = collection_point.id
  result = crud_create_order(customer, payload)

  assert result['status'] == 'ok'
  assert f'Clonato da ordine {original.id}' in result['order']['operator_note']
  refreshed = get_by_id(Order, original.id)
  assert refreshed.status == OrderStatus.RESCHEDULED
  assert refreshed.completion_date is not None
  assert "Rischedulato con l'ordine" in refreshed.operator_note


def test_filter_orders_formats_results(db):
  _, _, service_user, _ = customer_with_service()
  order = create_order()
  create_product(order, service_user, name='TV')

  result = filter_orders([])

  assert result['status'] == 'ok'
  assert len(result['orders']) == 1
  assert 'TV' in result['orders'][0]['products']


def test_get_order_raises_for_unknown_id(db):
  with pytest.raises(Exception, match='Numero di ordini trovati non valido'):
    get_order(424242)


def test_get_order_adds_delivery_position_when_booking(db):
  _, _, service_user, _ = customer_with_service()
  order = create_order(status=OrderStatus.BOOKING)
  create_product(order, service_user)
  delivery = create_user(UserRole.DELIVERY)
  create_delivery_info(delivery, lat=41.1, lon=16.8)
  schedule = create_schedule()
  link_order_to_schedule(order, schedule)
  create_delivery_group(delivery, schedule)
  create_schedule_item_user(delivery, schedule)

  result = get_order(order.id)

  assert result['status'] == 'ok'
  assert float(result['order']['lat']) == 41.1
  assert float(result['order']['lon']) == 16.8


def test_get_order_ignores_position_when_no_one_holds_it(db):
  """Senza un evento ScheduleItemUser attivo nessuno ha 'preso' la posizione:
  il corriere può avere una lat/lon salvata da un giro precedente, ma non va
  mostrata finché non riattiva esplicitamente la condivisione per il borderò."""
  _, _, service_user, _ = customer_with_service()
  order = create_order(status=OrderStatus.BOOKING)
  create_product(order, service_user)
  delivery = create_user(UserRole.DELIVERY)
  create_delivery_info(delivery, lat=41.1, lon=16.8)
  schedule = create_schedule()
  link_order_to_schedule(order, schedule)
  create_delivery_group(delivery, schedule)

  result = get_order(order.id)

  assert result['status'] == 'ok'
  assert 'lat' not in result['order']
  assert 'lon' not in result['order']


def test_get_order_ignores_position_after_closing(db):
  _, _, service_user, _ = customer_with_service()
  order = create_order(status=OrderStatus.BOOKING)
  create_product(order, service_user)
  delivery = create_user(UserRole.DELIVERY)
  create_delivery_info(delivery, lat=41.1, lon=16.8)
  schedule = create_schedule()
  link_order_to_schedule(order, schedule)
  create_delivery_group(delivery, schedule)
  create_schedule_item_user(delivery, schedule, type=ScheduleItemUserType.OPENING)
  create_schedule_item_user(delivery, schedule, type=ScheduleItemUserType.CLOSING)

  result = get_order(order.id)

  assert result['status'] == 'ok'
  assert 'lat' not in result['order']


def test_delete_order_rejects_scheduled_orders(db):
  order = create_order(status=OrderStatus.BOOKED)
  schedule = create_schedule()
  link_order_to_schedule(order, schedule)
  admin = create_user(UserRole.ADMIN)

  result = delete_order(admin, order.id)

  assert result['status'] == 'ko'
  assert get_by_id(Order, order.id) is not None


def test_delete_order_rejects_completed_orders(db):
  order = create_order(status=OrderStatus.DELIVERED)
  admin = create_user(UserRole.ADMIN)

  result = delete_order(admin, order.id)

  assert result['status'] == 'ko'


def test_delete_order_removes_waiting_order(db):
  order = create_order(status=OrderStatus.ACQUIRED)
  admin = create_user(UserRole.ADMIN)

  result = delete_order(admin, order.id)

  assert result['status'] == 'ok'
  assert get_by_id(Order, order.id) is None


def test_delete_order_removes_photo_files_after_commit(db, monkeypatch):
  from api.storage import session as session_module
  from database_api.operations import create
  from src.database.schema import Photo

  order = create_order(status=OrderStatus.ACQUIRED)
  create(Photo, {'order_id': order.id, 'link': 'http://x/order/photos/101.jpg'})
  create(Photo, {'order_id': order.id, 'link': 'http://x/order/photos/102.jpg'})
  admin = create_user(UserRole.ADMIN)

  deleted_files = []
  monkeypatch.setattr(
    session_module, 'delete_file', lambda filename, folder, **kwargs: deleted_files.append((filename, kwargs))
  )

  result = delete_order(admin, order.id)

  assert result['status'] == 'ok'
  assert get_by_id(Order, order.id) is None
  assert [filename for filename, _ in deleted_files] == ['101.jpg', '102.jpg']
  assert all(kwargs['subfolder'] == 'photos' for _, kwargs in deleted_files)


def test_delete_order_keeps_files_when_rejected(db, monkeypatch):
  from api.storage import session as session_module
  from database_api.operations import create
  from src.database.schema import Photo

  order = create_order(status=OrderStatus.DELIVERED)
  create(Photo, {'order_id': order.id, 'link': 'http://x/order/photos/103.jpg'})
  admin = create_user(UserRole.ADMIN)

  deleted_files = []
  monkeypatch.setattr(session_module, 'delete_file', lambda *args, **kwargs: deleted_files.append(args))

  result = delete_order(admin, order.id)

  assert result['status'] == 'ko'
  assert deleted_files == []


def test_update_order_booking_date_moves_to_booked(db):
  admin = create_user(UserRole.ADMIN)
  order = create_order(status=OrderStatus.ACQUIRED)

  with Session() as session:
    order_in_session = session.get(Order, order.id)
    update_order(admin, order_in_session, {'id': order.id, 'booking_date': '2026-07-25'}, session)
    session.commit()

  assert get_by_id(Order, order.id).status == OrderStatus.BOOKED


def test_update_order_completes_schedule_item(db):
  admin = create_user(UserRole.ADMIN)
  order = create_order(status=OrderStatus.BOOKING)
  schedule = create_schedule()
  item = link_order_to_schedule(order, schedule)

  with Session() as session:
    order_in_session = session.get(Order, order.id)
    update_order(admin, order_in_session, {'id': order.id, 'status': 'Delivered'}, session)
    session.commit()

  from src.database.schema import ScheduleItem

  assert get_by_id(ScheduleItem, item.id).completed is True
  assert get_by_id(Order, order.id).status == OrderStatus.DELIVERED


def test_update_order_closes_schedule_position_when_bordero_completed(db):
  admin = create_user(UserRole.ADMIN)
  delivery = create_user(UserRole.DELIVERY)
  order = create_order(status=OrderStatus.BOOKING)
  schedule = create_schedule()
  link_order_to_schedule(order, schedule)
  create_delivery_group(delivery, schedule)
  create_schedule_item_user(delivery, schedule)

  with Session() as session:
    order_in_session = session.get(Order, order.id)
    update_order(admin, order_in_session, {'id': order.id, 'status': 'Delivered'}, session)
    session.commit()

  from src.database.enum import ScheduleItemUserType
  from src.end_points.schedule.queries import get_latest_schedule_item_user

  latest = get_latest_schedule_item_user(schedule.id)
  assert latest.type == ScheduleItemUserType.CLOSING
  assert latest.user_id == delivery.id


def test_update_order_type_and_confirmed(db):
  admin = create_user(UserRole.ADMIN)
  order = create_order(order_type=OrderType.DELIVERY)

  with Session() as session:
    order_in_session = session.get(Order, order.id)
    update_order(
      admin,
      order_in_session,
      {'id': order.id, 'type': 'Withdraw', 'confirmed': True, 'external_status': 'New'},
      session,
    )
    session.commit()

  refreshed = get_by_id(Order, order.id)
  assert refreshed.type == OrderType.WITHDRAW
  assert refreshed.confirmed is True
  assert refreshed.confirmation_date is not None
  assert refreshed.external_status is None  # external_status viene scartato


def test_update_order_customer_requires_same_services(db):
  admin = create_user(UserRole.ADMIN)
  _, _, service_user, _ = customer_with_service()
  order = create_order()
  create_product(order, service_user)
  new_customer = create_user(UserRole.CUSTOMER)

  result = update_order_customer(admin, new_customer.id, order.id)

  assert result['status'] == 'ko'

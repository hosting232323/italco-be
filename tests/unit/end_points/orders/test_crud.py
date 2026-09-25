from datetime import date, time

import pytest

from database_api import Session, scope
from database_api.operations import create, get_by_id, update

from src.database.enum import OrderStatus, OrderType, ScheduleItemUserType, UserRole
from src.database.schema import DeliveryCoverageCap, DeliveryCoverageEntry, Order, Product
from src.end_points.orders.crud import (
  create_order as crud_create_order,
  delete_order,
  filter_orders,
  get_order,
  update_order,
  update_order_customer,
)
from src.end_points.orders.services import InvalidOrderProductsError

from tests.unit.factories import (
  assign_delivery_user_to_schedule,
  create_collection_point,
  create_delivery_info,
  create_company,
  create_order,
  create_product,
  create_schedule,
  create_schedule_item_user,
  create_service,
  create_service_user,
  create_transport,
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


def test_create_order_rejects_services_of_wrong_type(db):
  customer, service, _, collection_point = customer_with_service(order_type=OrderType.WITHDRAW)

  with pytest.raises(InvalidOrderProductsError, match='servizi selezionati'):
    crud_create_order(customer, _payload(service, collection_point))

  with Session() as session:
    assert session.query(Order).count() == 0
    assert session.query(Product).count() == 0


def test_create_order_rejects_products_from_another_company(db):
  admin = create_user(UserRole.ADMIN)
  other_company = create_company()
  with scope(company_id=other_company.id):
    customer, service, _, collection_point = customer_with_service()

  with pytest.raises(InvalidOrderProductsError, match='servizi selezionati'):
    crud_create_order(admin, _payload(service, collection_point, user_id=customer.id))

  with Session() as session:
    assert session.query(Order).count() == 0
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


def test_create_order_assigns_delivery_slot_from_coverage(db):
  # _payload usa cap='70121' e dpc='2026-07-20' (lunedì).
  customer, service, service_user, collection_point = customer_with_service()
  transport = create_transport()
  entry = create(
    DeliveryCoverageEntry,
    {'day_of_week': 0, 'transport_id': transport.id, 'start_time': time(8, 0), 'end_time': time(12, 0)},
  )
  create(DeliveryCoverageCap, {'entry_id': entry.id, 'cap': '70121'})

  result = crud_create_order(customer, _payload(service, collection_point))

  order = get_by_id(Order, result['order']['id'])
  assert (order.delivery_slot_start, order.delivery_slot_end) == (time(8, 0), time(12, 0))


def test_create_order_leaves_slot_empty_without_matching_coverage(db):
  customer, service, service_user, collection_point = customer_with_service()

  result = crud_create_order(customer, _payload(service, collection_point))

  order = get_by_id(Order, result['order']['id'])
  assert (order.delivery_slot_start, order.delivery_slot_end) == (None, None)


def test_create_order_does_not_assign_slot_when_created_by_admin(db):
  # Solo il cliente passa dal check-constraints/calendario vincolato: l'ordine
  # creato da un operatore/admin non ha un automatismo di fascia.
  admin = create_user(UserRole.ADMIN)
  customer, service, service_user, collection_point = customer_with_service()
  transport = create_transport()
  entry = create(
    DeliveryCoverageEntry,
    {'day_of_week': 0, 'transport_id': transport.id, 'start_time': time(8, 0), 'end_time': time(12, 0)},
  )
  create(DeliveryCoverageCap, {'entry_id': entry.id, 'cap': '70121'})

  result = crud_create_order(admin, _payload(service, collection_point, user_id=customer.id))

  order = get_by_id(Order, result['order']['id'])
  assert (order.delivery_slot_start, order.delivery_slot_end) == (None, None)


def test_create_order_uses_customer_chosen_slot_when_valid(db):
  # _payload usa cap='70121' e dpc='2026-07-20' (lunedì): due fasce coperte,
  # il cliente sceglie quella pomeridiana dal calendario invece di lasciare
  # decidere il bilanciamento automatico.
  customer, service, service_user, collection_point = customer_with_service()
  transport = create_transport()
  morning = create(
    DeliveryCoverageEntry,
    {'day_of_week': 0, 'transport_id': transport.id, 'start_time': time(8, 0), 'end_time': time(12, 0)},
  )
  create(DeliveryCoverageCap, {'entry_id': morning.id, 'cap': '70121'})
  afternoon = create(
    DeliveryCoverageEntry,
    {'day_of_week': 0, 'transport_id': transport.id, 'start_time': time(13, 0), 'end_time': time(18, 0)},
  )
  create(DeliveryCoverageCap, {'entry_id': afternoon.id, 'cap': '70121'})

  result = crud_create_order(
    customer,
    _payload(service, collection_point, delivery_slot_start='13:00', delivery_slot_end='18:00'),
  )

  order = get_by_id(Order, result['order']['id'])
  assert (order.delivery_slot_start, order.delivery_slot_end) == (time(13, 0), time(18, 0))


def test_create_order_ignores_customer_chosen_slot_when_not_covered(db):
  # Una fascia inventata (non corrisponde a nessun blocco) non va presa per
  # buona: si ricade sull'automatismo storico invece di salvare un valore
  # arbitrario mandato dal client.
  customer, service, service_user, collection_point = customer_with_service()
  transport = create_transport()
  entry = create(
    DeliveryCoverageEntry,
    {'day_of_week': 0, 'transport_id': transport.id, 'start_time': time(8, 0), 'end_time': time(12, 0)},
  )
  create(DeliveryCoverageCap, {'entry_id': entry.id, 'cap': '70121'})

  result = crud_create_order(
    customer,
    _payload(service, collection_point, delivery_slot_start='20:00', delivery_slot_end='22:00'),
  )

  order = get_by_id(Order, result['order']['id'])
  assert (order.delivery_slot_start, order.delivery_slot_end) == (time(8, 0), time(12, 0))


def test_create_order_leaves_slot_empty_when_customer_automatic_planning_is_off(db):
  # Punto vendita con pianificazione automatica spenta: la dpc resta manuale
  # anche se la copertura coprirebbe la data, come su main.
  customer = create_user(UserRole.CUSTOMER, automatic_planning=False)
  service = create_service()
  create_service_user(customer, service)
  collection_point = create_collection_point(customer, cap='70121')
  transport = create_transport()
  entry = create(
    DeliveryCoverageEntry,
    {'day_of_week': 0, 'transport_id': transport.id, 'start_time': time(8, 0), 'end_time': time(12, 0)},
  )
  create(DeliveryCoverageCap, {'entry_id': entry.id, 'cap': '70121'})

  result = crud_create_order(customer, _payload(service, collection_point))

  order = get_by_id(Order, result['order']['id'])
  assert (order.delivery_slot_start, order.delivery_slot_end) == (None, None)
  assert order.dpc == date(2026, 7, 20)


def test_create_order_ignores_client_sent_slot_when_customer_automatic_planning_is_off(db):
  # Enforcement lato server: anche se il client manda comunque uno slot
  # (client vecchio o manomesso), il punto vendita disabilitato lo ignora.
  customer = create_user(UserRole.CUSTOMER, automatic_planning=False)
  service = create_service()
  create_service_user(customer, service)
  collection_point = create_collection_point(customer, cap='70121')
  transport = create_transport()
  entry = create(
    DeliveryCoverageEntry,
    {'day_of_week': 0, 'transport_id': transport.id, 'start_time': time(8, 0), 'end_time': time(12, 0)},
  )
  create(DeliveryCoverageCap, {'entry_id': entry.id, 'cap': '70121'})

  result = crud_create_order(
    customer,
    _payload(service, collection_point, delivery_slot_start='08:00', delivery_slot_end='12:00'),
  )

  order = get_by_id(Order, result['order']['id'])
  assert (order.delivery_slot_start, order.delivery_slot_end) == (None, None)


def test_create_order_leaves_slot_empty_when_company_automatic_planning_is_off(db):
  update(db, {'automatic_planning': False})
  customer, service, service_user, collection_point = customer_with_service()
  transport = create_transport()
  entry = create(
    DeliveryCoverageEntry,
    {'day_of_week': 0, 'transport_id': transport.id, 'start_time': time(8, 0), 'end_time': time(12, 0)},
  )
  create(DeliveryCoverageCap, {'entry_id': entry.id, 'cap': '70121'})

  result = crud_create_order(customer, _payload(service, collection_point))

  order = get_by_id(Order, result['order']['id'])
  assert (order.delivery_slot_start, order.delivery_slot_end) == (None, None)


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
  assign_delivery_user_to_schedule(delivery, schedule)
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
  assign_delivery_user_to_schedule(delivery, schedule)

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
  assign_delivery_user_to_schedule(delivery, schedule)
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


def test_update_order_assigns_delivery_slot_when_customer_changes_dpc(db):
  customer = create_user(UserRole.CUSTOMER)
  transport = create_transport()
  entry = create(
    DeliveryCoverageEntry,
    {'day_of_week': 0, 'transport_id': transport.id, 'start_time': time(8, 0), 'end_time': time(12, 0)},
  )
  create(DeliveryCoverageCap, {'entry_id': entry.id, 'cap': '70121'})
  # 14/07/2026 è martedì: non coperto, lo slot nasce vuoto.
  order = create_order(cap='70121', dpc=date(2026, 7, 14))

  with Session() as session:
    order_in_session = session.get(Order, order.id)
    update_order(customer, order_in_session, {'id': order.id, 'dpc': '2026-07-20'}, session)  # lunedì, coperto
    session.commit()

  refreshed = get_by_id(Order, order.id)
  assert (refreshed.delivery_slot_start, refreshed.delivery_slot_end) == (time(8, 0), time(12, 0))


def test_update_order_clears_slot_when_customer_moves_outside_coverage(db):
  customer = create_user(UserRole.CUSTOMER)
  transport = create_transport()
  entry = create(
    DeliveryCoverageEntry,
    {'day_of_week': 0, 'transport_id': transport.id, 'start_time': time(8, 0), 'end_time': time(12, 0)},
  )
  create(DeliveryCoverageCap, {'entry_id': entry.id, 'cap': '70121'})
  order = create_order(
    cap='70121', dpc=date(2026, 7, 20), delivery_slot_start=time(8, 0), delivery_slot_end=time(12, 0)
  )

  with Session() as session:
    order_in_session = session.get(Order, order.id)
    update_order(customer, order_in_session, {'id': order.id, 'dpc': '2026-07-14'}, session)  # martedì, non coperto
    session.commit()

  refreshed = get_by_id(Order, order.id)
  assert (refreshed.delivery_slot_start, refreshed.delivery_slot_end) == (None, None)


def test_update_order_uses_customer_chosen_slot_when_valid(db):
  customer = create_user(UserRole.CUSTOMER)
  transport = create_transport()
  morning = create(
    DeliveryCoverageEntry,
    {'day_of_week': 0, 'transport_id': transport.id, 'start_time': time(8, 0), 'end_time': time(12, 0)},
  )
  create(DeliveryCoverageCap, {'entry_id': morning.id, 'cap': '70121'})
  afternoon = create(
    DeliveryCoverageEntry,
    {'day_of_week': 0, 'transport_id': transport.id, 'start_time': time(13, 0), 'end_time': time(18, 0)},
  )
  create(DeliveryCoverageCap, {'entry_id': afternoon.id, 'cap': '70121'})
  order = create_order(cap='70121', dpc=date(2026, 7, 20))

  with Session() as session:
    order_in_session = session.get(Order, order.id)
    update_order(
      customer,
      order_in_session,
      {'id': order.id, 'dpc': '2026-07-20', 'delivery_slot_start': '13:00', 'delivery_slot_end': '18:00'},
      session,
    )
    session.commit()

  refreshed = get_by_id(Order, order.id)
  assert (refreshed.delivery_slot_start, refreshed.delivery_slot_end) == (time(13, 0), time(18, 0))


def test_update_order_does_not_touch_slot_when_edited_by_operator(db):
  admin = create_user(UserRole.ADMIN)
  order = create_order(dpc=date(2026, 7, 13), delivery_slot_start=time(9, 0), delivery_slot_end=time(11, 0))

  with Session() as session:
    order_in_session = session.get(Order, order.id)
    update_order(admin, order_in_session, {'id': order.id, 'dpc': '2026-07-20'}, session)
    session.commit()

  refreshed = get_by_id(Order, order.id)
  assert (refreshed.delivery_slot_start, refreshed.delivery_slot_end) == (time(9, 0), time(11, 0))


def test_update_order_recomputes_slot_excluding_itself_from_the_count(db):
  # Il cliente riconferma la stessa dpc (es. tocca un altro campo del form
  # date): il ricalcolo scatta comunque perché 'dpc' è nel payload, ma lo
  # slot già assegnato all'ordine non deve contare contro se stesso nel
  # confronto tra le fasce, altrimenti lo spingerebbe via da quella corretta.
  customer = create_user(UserRole.CUSTOMER)
  transport = create_transport()
  busy = create(
    DeliveryCoverageEntry,
    {'day_of_week': 0, 'transport_id': transport.id, 'start_time': time(8, 0), 'end_time': time(12, 0)},
  )
  create(DeliveryCoverageCap, {'entry_id': busy.id, 'cap': '70121'})
  create(
    DeliveryCoverageEntry,
    {'day_of_week': 0, 'transport_id': transport.id, 'start_time': time(13, 0), 'end_time': time(18, 0)},
  )
  order = create_order(
    cap='70121', dpc=date(2026, 7, 20), delivery_slot_start=time(8, 0), delivery_slot_end=time(12, 0)
  )

  with Session() as session:
    order_in_session = session.get(Order, order.id)
    update_order(customer, order_in_session, {'id': order.id, 'dpc': '2026-07-20'}, session)
    session.commit()

  refreshed = get_by_id(Order, order.id)
  assert (refreshed.delivery_slot_start, refreshed.delivery_slot_end) == (time(8, 0), time(12, 0))


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
  assign_delivery_user_to_schedule(delivery, schedule)
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


def test_update_order_type_replaces_product_using_new_service_type(db):
  admin = create_user(UserRole.ADMIN)
  customer, _, delivery_service_user, collection_point = customer_with_service()
  check_service = create_service(OrderType.CHECK)
  check_service_user = create_service_user(customer, check_service, price=20)
  order = create_order(order_type=OrderType.DELIVERY)
  create_product(order, delivery_service_user, name='Lavatrice')

  with Session() as session:
    order_in_session = session.get(Order, order.id)
    update_order(
      admin,
      order_in_session,
      {
        'id': order.id,
        'type': 'Check',
        'user_id': customer.id,
        'products': {
          'Lavatrice..': {
            'services': [{'id': check_service.id}],
            'collection_point': {'id': collection_point.id},
          }
        },
      },
      session,
    )
    session.commit()

  with Session() as session:
    refreshed = session.get(Order, order.id)
    products = session.query(Product).filter(Product.order_id == order.id).all()
    assert refreshed.type == OrderType.CHECK
    assert [(product.name, product.service_user_id) for product in products] == [('Lavatrice..', check_service_user.id)]


def test_update_order_customer_requires_same_services(db):
  admin = create_user(UserRole.ADMIN)
  _, _, service_user, _ = customer_with_service()
  order = create_order()
  create_product(order, service_user)
  new_customer = create_user(UserRole.CUSTOMER)

  result = update_order_customer(admin, new_customer.id, order.id)

  assert result['status'] == 'ko'

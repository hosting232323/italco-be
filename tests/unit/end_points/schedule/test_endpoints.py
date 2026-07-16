from datetime import date

from database_api import Session
from database_api.operations import get_by_id

from src.database.enum import OrderStatus, ScheduleType, UserRole
from src.database.schema import (
  DeliveryGroup,
  Order,
  Schedule,
  ScheduleItem,
  ScheduleItemCollectionPoint,
  ScheduleItemOrder,
)

from tests.unit.factories import (
  auth_header,
  create_delivery_group,
  create_delivery_info,
  create_order,
  create_product,
  create_schedule,
  create_transport,
  create_user,
  customer_with_service,
  link_order_to_schedule,
)


def _schedule_payload(transport, order, collection_point, users):
  return {
    'date': date.today().strftime('%Y-%m-%d'),
    'transport_id': transport.id,
    'users': [{'id': user.id} for user in users],
    'schedule_items': [
      {
        'index': 0,
        'operation_type': 'CollectionPoint',
        'collection_point_id': collection_point.id,
        'start_time_slot': '08:00',
        'end_time_slot': '09:00',
      },
      {
        'index': 1,
        'operation_type': 'Order',
        'order_id': order.id,
        'start_time_slot': '09:00',
        'end_time_slot': '11:00',
      },
    ],
  }


def _booked_order(service_user):
  order = create_order(status=OrderStatus.BOOKED)
  create_product(order, service_user)
  return order


def test_create_schedule_full_flow(client):
  operator = create_user(UserRole.OPERATOR)
  _, _, service_user, collection_point = customer_with_service()
  order = _booked_order(service_user)
  transport = create_transport()
  delivery = create_user(UserRole.DELIVERY)

  response = client.post(
    '/schedule',
    json=_schedule_payload(transport, order, collection_point, [delivery]),
    headers=auth_header(operator),
  )

  body = response.get_json()
  assert body['status'] == 'ok'
  schedule_id = body['schedule']['id']
  with Session() as session:
    items = session.query(ScheduleItem).filter_by(schedule_id=schedule_id).all()
    assert {item.operation_type for item in items} == {ScheduleType.ORDER, ScheduleType.COLLECTIONPOINT}
    assert session.query(DeliveryGroup).filter_by(schedule_id=schedule_id).count() == 1
    assert session.query(ScheduleItemOrder).count() == 1
    assert session.query(ScheduleItemCollectionPoint).count() == 1
  # Ordine senza transport_id sui prodotti -> Scheduled
  assert get_by_id(Order, order.id).status == OrderStatus.SCHEDULED


def test_create_schedule_marks_booking_when_products_have_transport(client):
  operator = create_user(UserRole.OPERATOR)
  _, _, service_user, collection_point = customer_with_service()
  transport = create_transport()
  order = create_order(status=OrderStatus.BOOKED)
  create_product(order, service_user, transport_id=transport.id)
  delivery = create_user(UserRole.DELIVERY)

  response = client.post(
    '/schedule',
    json=_schedule_payload(transport, order, collection_point, [delivery]),
    headers=auth_header(operator),
  )

  assert response.get_json()['status'] == 'ok'
  assert get_by_id(Order, order.id).status == OrderStatus.BOOKING


def test_create_schedule_rejects_already_assigned_delivery(client):
  operator = create_user(UserRole.OPERATOR)
  _, _, service_user, collection_point = customer_with_service()
  order = _booked_order(service_user)
  transport = create_transport()
  delivery = create_user(UserRole.DELIVERY)
  create_delivery_group(delivery, create_schedule(schedule_date=date.today()))

  response = client.post(
    '/schedule',
    json=_schedule_payload(transport, order, collection_point, [delivery]),
    headers=auth_header(operator),
  )

  body = response.get_json()
  assert body['status'] == 'ko'
  assert 'già assegnato' in body['message']


def test_create_schedule_rejects_missing_orders(client):
  operator = create_user(UserRole.OPERATOR)
  transport = create_transport()
  delivery = create_user(UserRole.DELIVERY)

  response = client.post(
    '/schedule',
    json={
      'date': date.today().strftime('%Y-%m-%d'),
      'transport_id': transport.id,
      'users': [{'id': delivery.id}],
      'schedule_items': [],
    },
    headers=auth_header(operator),
  )

  body = response.get_json()
  assert body['status'] == 'ko'
  assert 'Errore nella creazione del borderò' in body['message']


def test_delete_schedule_restores_orders(client):
  admin = create_user(UserRole.ADMIN)
  _, _, service_user, _ = customer_with_service()
  order = create_order(status=OrderStatus.SCHEDULED)
  create_product(order, service_user)
  schedule = create_schedule()
  link_order_to_schedule(order, schedule)
  create_delivery_group(create_user(UserRole.DELIVERY), schedule)

  response = client.delete(f'/schedule/{schedule.id}', headers=auth_header(admin))

  assert response.get_json()['status'] == 'ok'
  assert get_by_id(Schedule, schedule.id) is None
  assert get_by_id(Order, order.id).status == OrderStatus.BOOKED
  with Session() as session:
    assert session.query(ScheduleItem).count() == 0
    assert session.query(DeliveryGroup).count() == 0


def test_filter_schedules(client):
  operator = create_user(UserRole.OPERATOR)
  _, _, service_user, _ = customer_with_service()
  order = create_order(status=OrderStatus.SCHEDULED)
  create_product(order, service_user)
  schedule = create_schedule()
  link_order_to_schedule(order, schedule)
  delivery = create_user(UserRole.DELIVERY)
  create_delivery_group(delivery, schedule)

  response = client.post(
    '/schedule/filter',
    json={'filters': [{'model': 'Schedule', 'field': 'id', 'value': schedule.id}]},
    headers=auth_header(operator),
  )

  body = response.get_json()
  assert body['status'] == 'ok'
  assert len(body['schedules']) == 1
  assert body['schedules'][0]['id'] == schedule.id
  assert [user['id'] for user in body['schedules'][0]['users']] == [delivery.id]
  assert len(body['schedules'][0]['schedule_items']) == 1


def test_filter_schedules_by_order_id_adds_sibling_items(client):
  operator = create_user(UserRole.OPERATOR)
  _, _, service_user, _ = customer_with_service()
  first_order = create_order(status=OrderStatus.SCHEDULED)
  create_product(first_order, service_user)
  second_order = create_order(status=OrderStatus.SCHEDULED)
  create_product(second_order, service_user)
  schedule = create_schedule()
  link_order_to_schedule(first_order, schedule, index=0)
  link_order_to_schedule(second_order, schedule, index=1)
  create_delivery_group(create_user(UserRole.DELIVERY), schedule)

  response = client.post(
    '/schedule/filter',
    json={'filters': [{'model': 'Order', 'field': 'id', 'value': first_order.id}]},
    headers=auth_header(operator),
  )

  body = response.get_json()
  assert body['status'] == 'ok'
  item_order_ids = {item['order_id'] for item in body['schedules'][0]['schedule_items']}
  # Con il filtro per ordine vengono aggiunti anche gli altri item del borderò
  assert item_order_ids == {first_order.id, second_order.id}


def test_update_schedule_replaces_users_and_items(client):
  operator = create_user(UserRole.OPERATOR)
  _, _, service_user, collection_point = customer_with_service()
  order = create_order(status=OrderStatus.SCHEDULED)
  create_product(order, service_user)
  schedule = create_schedule()
  existing_item = link_order_to_schedule(order, schedule, index=0)
  old_delivery = create_user(UserRole.DELIVERY)
  create_delivery_group(old_delivery, schedule)
  new_delivery = create_user(UserRole.DELIVERY)
  new_order = create_order(status=OrderStatus.BOOKED)
  create_product(new_order, service_user)

  response = client.put(
    f'/schedule/{schedule.id}',
    json={
      'date': date.today().strftime('%Y-%m-%d'),
      'transport_id': schedule.transport_id,
      'deleted_users': [old_delivery.id],
      'users': [{'id': new_delivery.id}],
      'schedule_items': [
        {
          'id': existing_item.id,
          'index': 1,
          'operation_type': 'Order',
          'order_id': order.id,
          'start_time_slot': '10:00',
          'end_time_slot': '12:00',
        },
        {
          'index': 0,
          'operation_type': 'Order',
          'order_id': new_order.id,
          'start_time_slot': '08:00',
          'end_time_slot': '10:00',
        },
      ],
    },
    headers=auth_header(operator),
  )

  body = response.get_json()
  assert body['status'] == 'ok'
  with Session() as session:
    delivery_groups = session.query(DeliveryGroup).filter_by(schedule_id=schedule.id).all()
    assert [group.user_id for group in delivery_groups] == [new_delivery.id]
    updated_item = session.get(ScheduleItem, existing_item.id)
    assert updated_item.index == 1
    assert session.query(ScheduleItemOrder).count() == 2


def test_pianification_requires_known_orders(client):
  operator = create_user(UserRole.OPERATOR)

  response = client.post('/schedule/pianification', json={'orders_id': [99999]}, headers=auth_header(operator))

  body = response.get_json()
  assert body['status'] == 'ko'
  assert body['message'] == 'Ordini non identificati'


def test_pianification_requires_booked_status(client):
  operator = create_user(UserRole.OPERATOR)
  _, _, service_user, _ = customer_with_service()
  order = create_order(status=OrderStatus.ACQUIRED)
  create_product(order, service_user)

  response = client.post(
    '/schedule/pianification', json={'orders_id': [order.id]}, headers=auth_header(operator)
  )

  body = response.get_json()
  assert body['status'] == 'ko'
  assert 'non sono in stato Booked' in body['message']


def test_pianification_builds_schedule_items(client):
  operator = create_user(UserRole.OPERATOR)
  _, _, service_user, collection_point = customer_with_service()
  order = create_order(status=OrderStatus.BOOKED)
  create_product(order, service_user, collection_point_id=collection_point.id)

  response = client.post(
    '/schedule/pianification', json={'orders_id': [order.id]}, headers=auth_header(operator)
  )

  body = response.get_json()
  assert body['status'] == 'ok'
  operation_types = [item['operation_type'] for item in body['schedule_items']]
  assert operation_types == ['CollectionPoint', 'Order']


def test_suggestions_endpoint_requires_orders(client):
  admin = create_user(UserRole.ADMIN)

  response = client.get(
    '/schedule/suggestions?work_date=2026-07-15&min_size_group=1&max_size_group=5&max_distance_km=10',
    headers=auth_header(admin),
  )

  body = response.get_json()
  assert body['status'] == 'ko'
  assert body['message'] == 'Ordini non trovati in questa data'


def test_suggestions_endpoint_returns_groups(client):
  admin = create_user(UserRole.ADMIN)
  _, _, service_user, collection_point = customer_with_service()
  order = create_order(status=OrderStatus.BOOKED, dpc=date(2026, 7, 15), cap='70121')
  create_product(order, service_user, collection_point_id=collection_point.id)
  delivery = create_user(UserRole.DELIVERY)
  create_delivery_info(delivery, cap='70121')
  transport = create_transport()

  response = client.get(
    '/schedule/suggestions?work_date=2026-07-15&min_size_group=1&max_size_group=5&max_distance_km=10',
    headers=auth_header(admin),
  )

  body = response.get_json()
  assert body['status'] == 'ok'
  assert [user['id'] for user in body['delivery_users']] == [delivery.id]
  assert [t['id'] for t in body['transports']] == [transport.id]
  assert len(body['groups']) == 1
  assert body['groups'][0]['delivery_users'][0]['id'] == delivery.id

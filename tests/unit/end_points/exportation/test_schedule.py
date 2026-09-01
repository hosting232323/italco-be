from src.database.enum import OrderStatus, UserRole

from tests.unit.factories import (
  auth_header,
  create_delivery_group,
  create_order,
  create_product,
  create_schedule,
  create_user,
  customer_with_service,
  link_order_to_schedule,
)


def test_export_schedule_returns_pdf(client):
  admin = create_user(UserRole.ADMIN)
  _, _, service_user, collection_point = customer_with_service()
  order = create_order(status=OrderStatus.SCHEDULED, signature=b'\x89PNG-fake')
  create_product(order, service_user, collection_point_id=collection_point.id)
  schedule = create_schedule()
  link_order_to_schedule(order, schedule)
  create_delivery_group(create_user(UserRole.DELIVERY), schedule)

  response = client.get(f'/export/schedule/{schedule.id}', headers=auth_header(admin))

  assert response.status_code == 200
  assert response.headers['Content-Type'] == 'application/pdf'
  assert response.get_data().startswith(b'%PDF')


def test_export_schedule_without_collection_point_returns_pdf(client):
  admin = create_user(UserRole.ADMIN)
  _, _, service_user, _ = customer_with_service()
  order = create_order(status=OrderStatus.SCHEDULED)
  create_product(order, service_user)
  schedule = create_schedule()
  link_order_to_schedule(order, schedule)
  create_delivery_group(create_user(UserRole.DELIVERY), schedule)

  response = client.get(f'/export/schedule/{schedule.id}', headers=auth_header(admin))

  assert response.status_code == 200
  assert response.headers['Content-Type'] == 'application/pdf'
  assert response.get_data().startswith(b'%PDF')


def test_export_schedule_not_found(client):
  admin = create_user(UserRole.ADMIN)

  response = client.get('/export/schedule/999999', headers=auth_header(admin))

  body = response.get_json()
  assert body['status'] == 'ko'
  assert body['message'] == 'Numero di borderò trovati non valido'

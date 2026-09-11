from io import BytesIO
from datetime import date

from pypdf import PdfReader

from src.database.enum import OrderStatus, UserRole

from tests.unit.factories import (
  auth_header,
  create_delivery_group,
  create_order,
  create_product,
  create_rae_disposal_place,
  create_rae_product,
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


def test_export_schedule_prints_the_chosen_rae_disposal_place(client):
  # Il luogo di smaltimento è scelto una volta sola sul borderò (non sul
  # Disposal, che a questo punto non esiste ancora): il DDT RAEE incorporato
  # nel PDF del borderò deve mostrarlo comunque, senza aspettare lo smaltimento
  # vero e proprio.
  admin = create_user(UserRole.ADMIN)
  customer, _, service_user, _ = customer_with_service()
  order = create_order(status=OrderStatus.SCHEDULED)
  rae_product = create_rae_product(order, customer, dtr_date=date.today())
  create_product(order, service_user, rae_product_id=rae_product.id)
  disposal_place = create_rae_disposal_place(rae_grouping_place='Deposito Test')
  schedule = create_schedule(rae_disposal_place_id=disposal_place.id)
  link_order_to_schedule(order, schedule)
  create_delivery_group(create_user(UserRole.DELIVERY), schedule)

  response = client.get(f'/export/schedule/{schedule.id}', headers=auth_header(admin))

  text = ''.join(page.extract_text() for page in PdfReader(BytesIO(response.data)).pages)
  assert 'Deposito Test' in text


def test_export_schedule_not_found(client):
  admin = create_user(UserRole.ADMIN)

  response = client.get('/export/schedule/999999', headers=auth_header(admin))

  body = response.get_json()
  assert body['status'] == 'ko'
  assert body['message'] == 'Numero di borderò trovati non valido'

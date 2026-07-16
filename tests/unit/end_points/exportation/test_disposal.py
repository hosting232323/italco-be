from datetime import date

from src.database.enum import RaeStatus, UserRole
from src.end_points.exportation.disposal import format_row

from tests.unit.factories import (
  auth_header,
  create_carrier,
  create_collection_center,
  create_disposal,
  create_order,
  create_product,
  create_rae_product,
  create_rae_product_group,
  create_schedule,
  create_user,
  customer_with_service,
  link_order_to_schedule,
)


def _disposal_with_products(quantity=2, group_code='R1'):
  carrier = create_carrier()
  center = create_collection_center()
  disposal = create_disposal(carrier, center)
  customer = create_user(UserRole.CUSTOMER)
  group = create_rae_product_group(group_code=group_code)
  order = create_order(addressee='Cliente Smaltimento')
  create_rae_product(
    order, customer, group, disposal_id=disposal.id, quantity=quantity, status=RaeStatus.DISPOSED_OFF, number=5
  )
  return disposal, order, customer


def test_export_attached_a_returns_pdf(client):
  operator = create_user(UserRole.OPERATOR)
  disposal, _, _ = _disposal_with_products()

  response = client.get(f'/export/disposal/{disposal.id}/attached-1', headers=auth_header(operator))

  assert response.status_code == 200
  assert response.headers['Content-Type'] == 'application/pdf'


def test_export_attached_a_missing_disposal(client):
  operator = create_user(UserRole.OPERATOR)

  response = client.get('/export/disposal/999999/attached-1', headers=auth_header(operator))

  body = response.get_json()
  assert body['status'] == 'ko'
  assert body['message'] == 'Smaltimento non trovato'


def test_export_attached_a_without_rae_products(client):
  operator = create_user(UserRole.OPERATOR)
  disposal = create_disposal()

  response = client.get(f'/export/disposal/{disposal.id}/attached-1', headers=auth_header(operator))

  body = response.get_json()
  assert body['status'] == 'ko'
  assert 'Nessun prodotto RAE' in body['message']


def test_export_attached_b_returns_pdf(client):
  operator = create_user(UserRole.OPERATOR)
  disposal, _, _ = _disposal_with_products()

  response = client.get(f'/export/disposal/{disposal.id}/attached-2', headers=auth_header(operator))

  assert response.status_code == 200
  assert response.headers['Content-Type'] == 'application/pdf'


def test_export_attached_b_wrong_disposal_count(client):
  operator = create_user(UserRole.OPERATOR)

  response = client.get('/export/disposal/999999/attached-2', headers=auth_header(operator))

  body = response.get_json()
  assert body['status'] == 'ko'
  assert body['message'] == 'Numero di smaltimenti trovati non valido'


def test_export_card_index_returns_pdf(client):
  operator = create_user(UserRole.OPERATOR)
  disposal, _, _ = _disposal_with_products()

  response = client.get(f'/export/disposal/{disposal.id}/card-index', headers=auth_header(operator))

  assert response.status_code == 200
  assert response.headers['Content-Type'] == 'application/pdf'


def test_export_card_index_missing_disposal(client):
  operator = create_user(UserRole.OPERATOR)

  response = client.get('/export/disposal/999999/card-index', headers=auth_header(operator))

  assert response.get_json()['message'] == 'Smaltimento non trovato'


def test_format_row_uses_schedule_date(db):
  customer, _, service_user, _ = customer_with_service()
  order = create_order(addressee='Con borderò')
  create_product(order, service_user)
  schedule = create_schedule(schedule_date=date(2026, 7, 12))
  link_order_to_schedule(order, schedule)
  group = create_rae_product_group(group_code='R3')
  rae_product = create_rae_product(order, customer, group, quantity=4, number=9)

  row = format_row(rae_product, group, customer, order)

  assert row['dtr'] == '12/07/2026'
  assert row['n_ddt'] == 9
  assert row['raggruppamento'] == 'R3'
  assert row['quantita'] == 4
  assert row['destinatario'] == 'Con borderò'


def test_format_row_without_schedule_uses_placeholder(db):
  customer, _, service_user, _ = customer_with_service()
  order = create_order()
  create_product(order, service_user)
  group = create_rae_product_group()
  rae_product = create_rae_product(order, customer, group)

  row = format_row(rae_product, group, customer, order)

  assert row['dtr'] == '/'

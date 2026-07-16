from datetime import date

from src.database.enum import OrderStatus, UserRole

from tests.unit.factories import auth_header, create_order, create_product, create_user, customer_with_service


def test_export_invoice_returns_pdf_for_delivered_orders(client):
  admin = create_user(UserRole.ADMIN)
  _, _, service_user, _ = customer_with_service(price=42.0)
  order = create_order(status=OrderStatus.DELIVERED, booking_date=date(2026, 7, 10))
  create_product(order, service_user)

  response = client.post(
    '/export/invoice',
    json={'filters': [{'model': 'Order', 'field': 'booking_date', 'value': ['2026-07-01', '2026-07-31']}]},
    headers=auth_header(admin),
  )

  assert response.status_code == 200
  assert response.headers['Content-Type'] == 'application/pdf'


def test_export_invoice_fails_without_delivered_orders(client):
  admin = create_user(UserRole.ADMIN)
  _, _, service_user, _ = customer_with_service()
  order = create_order(status=OrderStatus.ACQUIRED, booking_date=date(2026, 7, 10))
  create_product(order, service_user)

  response = client.post(
    '/export/invoice',
    json={'filters': [{'model': 'Order', 'field': 'booking_date', 'value': ['2026-07-01', '2026-07-31']}]},
    headers=auth_header(admin),
  )

  body = response.get_json()
  assert body['status'] == 'ko'
  assert body['message'] == 'Numero di ordini trovati non valido'


def test_export_invoice_requires_admin(client):
  operator = create_user(UserRole.OPERATOR)

  response = client.post('/export/invoice', json={'filters': []}, headers=auth_header(operator))

  assert response.get_json()['status'] == 'session'

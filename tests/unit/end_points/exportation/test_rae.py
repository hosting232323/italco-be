from datetime import date

from src.database.enum import RaeStatus, UserRole
from src.end_points.exportation.rae import get_rae_export_info_by_order

from tests.unit.factories import (
  auth_header,
  create_order,
  create_product,
  create_rae_product,
  create_user,
  customer_with_service,
)


def _order_with_emitted_rae():
  customer, _, service_user, _ = customer_with_service()
  order = create_order()
  rae_product = create_rae_product(
    order, customer, status=RaeStatus.EMITTED, dtr_date=date.today(), number=7
  )
  create_product(order, service_user, rae_product_id=rae_product.id)
  return customer, order, rae_product


def test_export_rae_by_order_returns_pdf(client):
  admin = create_user(UserRole.ADMIN)
  _, order, _ = _order_with_emitted_rae()

  response = client.get(f'/export/rae/{order.id}', headers=auth_header(admin))

  assert response.status_code == 200
  assert response.headers['Content-Type'] == 'application/pdf'


def test_export_rae_by_order_without_rae_products(client):
  admin = create_user(UserRole.ADMIN)
  _, _, service_user, _ = customer_with_service()
  order = create_order()
  create_product(order, service_user)

  response = client.get(f'/export/rae/{order.id}', headers=auth_header(admin))

  body = response.get_json()
  assert body['status'] == 'ko'
  assert body['message'] == 'Nessun prodotto rae identificato'


def test_export_rae_by_order_unknown_order(client):
  admin = create_user(UserRole.ADMIN)

  response = client.get('/export/rae/999999', headers=auth_header(admin))

  assert response.get_json()['status'] == 'ko'


def test_export_rae_by_product_returns_pdf(client):
  admin = create_user(UserRole.ADMIN)
  _, _, rae_product = _order_with_emitted_rae()

  response = client.get(f'/export/rae/product/{rae_product.id}', headers=auth_header(admin))

  assert response.status_code == 200
  assert response.headers['Content-Type'] == 'application/pdf'


def test_export_rae_by_product_rejects_generated_status(client):
  admin = create_user(UserRole.ADMIN)
  customer, _, service_user, _ = customer_with_service()
  order = create_order()
  rae_product = create_rae_product(order, customer, status=RaeStatus.GENERATED)
  create_product(order, service_user, rae_product_id=rae_product.id)

  response = client.get(f'/export/rae/product/{rae_product.id}', headers=auth_header(admin))

  body = response.get_json()
  assert body['status'] == 'ko'
  assert body['message'] == 'Prodotto rae non ancora emesso'


def test_export_rae_by_product_unknown_product(client):
  admin = create_user(UserRole.ADMIN)

  response = client.get('/export/rae/product/999999', headers=auth_header(admin))

  body = response.get_json()
  assert body['status'] == 'ko'
  assert body['message'] == 'Prodotto rae non trovato'


def test_get_rae_export_info_by_order_requires_dtr_date():
  order_dict = {
    'products': {
      'ConDtr': {'rae_product': {'id': 1, 'dtr_date': '2026-07-15'}},
      'SenzaDtr': {'rae_product': {'id': 2}},
      'SenzaRae': {},
    }
  }

  results = get_rae_export_info_by_order(order_dict)

  assert [entry['id'] for entry in results] == [1]

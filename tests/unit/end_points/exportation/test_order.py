from io import BytesIO

from pypdf import PdfReader

from src.database.enum import UserRole

from tests.unit.factories import (
  auth_header,
  create_customer_info,
  create_order,
  create_product,
  create_user,
  customer_with_service,
)


def test_export_order_returns_pdf(client):
  admin = create_user(UserRole.ADMIN)
  _, _, service_user, collection_point = customer_with_service()
  order = create_order(signature=b'\x89PNG-fake')
  create_product(order, service_user, collection_point_id=collection_point.id)

  response = client.get(f'/export/order/{order.id}', headers=auth_header(admin))

  assert response.status_code == 200
  assert response.headers['Content-Type'] == 'application/pdf'
  assert response.get_data().startswith(b'%PDF')


def test_export_order_without_collection_point_returns_pdf(client):
  admin = create_user(UserRole.ADMIN)
  _, _, service_user, _ = customer_with_service()
  order = create_order()
  create_product(order, service_user)

  response = client.get(f'/export/order/{order.id}', headers=auth_header(admin))

  assert response.status_code == 200
  assert response.headers['Content-Type'] == 'application/pdf'
  assert response.get_data().startswith(b'%PDF')


def test_export_order_pdf_carries_the_company_letterhead(client):
  admin = create_user(UserRole.ADMIN)
  _, _, service_user, collection_point = customer_with_service()
  order = create_order()
  create_product(order, service_user, collection_point_id=collection_point.id)

  response = client.get(f'/export/order/{order.id}', headers=auth_header(admin))

  text = ''.join(page.extract_text() for page in PdfReader(BytesIO(response.data)).pages)
  assert 'Test Company SRL' in text
  assert 'P. IVA 09876543210' in text
  assert 'C.F. 01234567890' in text
  assert 'Hubstra' in text


def _order_pdf_text(client, admin, preloaded):
  _, _, service_user, collection_point = customer_with_service()
  order = create_order(preloaded=preloaded)
  create_product(order, service_user, collection_point_id=collection_point.id)

  response = client.get(f'/export/order/{order.id}', headers=auth_header(admin))

  return ''.join(page.extract_text() for page in PdfReader(BytesIO(response.data)).pages)


def test_export_order_pdf_shows_the_preloaded_row_only_when_preloaded(client):
  admin = create_user(UserRole.ADMIN)

  assert 'Precaricato' in _order_pdf_text(client, admin, True)
  assert 'Precaricato' not in _order_pdf_text(client, admin, False)


def test_export_order_not_found(client):
  admin = create_user(UserRole.ADMIN)

  response = client.get('/export/order/999999', headers=auth_header(admin))

  body = response.get_json()
  assert body['status'] == 'ko'
  assert body['message'] == 'Numero di ordini trovati non valido'


def test_export_order_customer_cannot_export_foreign_orders(client):
  customer, _, _, _ = customer_with_service()
  _, _, other_service_user, _ = customer_with_service()
  foreign_order = create_order()
  create_product(foreign_order, other_service_user)

  response = client.get(f'/export/order/{foreign_order.id}', headers=auth_header(customer))

  assert response.get_json()['status'] == 'ko'


def test_export_order_customer_exports_own_order(client):
  customer, _, service_user, collection_point = customer_with_service()
  order = create_order()
  create_product(order, service_user, collection_point_id=collection_point.id)

  response = client.get(f'/export/order/{order.id}', headers=auth_header(customer))

  assert response.headers['Content-Type'] == 'application/pdf'


def test_export_order_pdf_prints_the_selling_point_registry_as_committente(client):
  admin = create_user(UserRole.ADMIN)
  customer, _, service_user, collection_point = customer_with_service()
  create_customer_info(customer, company_name='Rossi SRL', address='Via Roma 1', city='Bari', tax_code='01234567890')
  order = create_order()
  create_product(order, service_user, collection_point_id=collection_point.id)

  response = client.get(f'/export/order/{order.id}', headers=auth_header(admin))

  text = ' '.join(''.join(page.extract_text() for page in PdfReader(BytesIO(response.data)).pages).split())
  assert 'Rossi SRL, Via Roma 1, Bari, C.F./P.IVA 01234567890' in text

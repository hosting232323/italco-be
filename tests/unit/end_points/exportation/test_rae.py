import re
from io import BytesIO
from datetime import date

from pypdf import PdfReader

from src.database.enum import RaeStatus, UserRole
from src.end_points.exportation.rae import _has_long_word, get_rae_export_info_by_order

from tests.unit.factories import (
  auth_header,
  create_dtr_document,
  create_order,
  create_product,
  create_rae_product,
  create_user,
  customer_with_service,
)


def _order_with_emitted_rae():
  customer, _, service_user, _ = customer_with_service()
  order = create_order()
  rae_product = create_rae_product(order, customer, status=RaeStatus.EMITTED, dtr_date=date.today(), number=7)
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


def test_export_rae_card_index_returns_pdf(client):
  operator = create_user(UserRole.OPERATOR)
  customer, _, _ = _order_with_emitted_rae()

  response = client.get(f'/export/rae/card-index/{customer.id}/{date.today().year}', headers=auth_header(operator))

  assert response.status_code == 200
  assert response.headers['Content-Type'] == 'application/pdf'


def test_export_rae_card_index_shows_pickup_status(client):
  operator = create_user(UserRole.OPERATOR)
  customer, _, _ = _order_with_emitted_rae()

  response = client.get(f'/export/rae/card-index/{customer.id}/{date.today().year}', headers=auth_header(operator))

  assert response.status_code == 200
  text = ''.join(page.extract_text() for page in PdfReader(BytesIO(response.data)).pages)
  assert 'Stato' in text
  assert 'Emesso' in text
  # La colonna raggruppamento e' abbreviata per far posto allo stato.
  assert 'Grup.' in text
  assert 'Raggrupp.' not in text
  # Il punto vendita compare solo nel riquadro in testa, non su ogni riga.
  assert text.count(customer.nickname) == 1


def test_export_rae_card_index_unknown_selling_point(client):
  operator = create_user(UserRole.OPERATOR)

  response = client.get(f'/export/rae/card-index/999999/{date.today().year}', headers=auth_header(operator))

  body = response.get_json()
  assert body['status'] == 'ko'
  assert body['message'] == 'Punto vendita non trovato'


def test_export_rae_card_index_rejects_non_customer_user(client):
  operator = create_user(UserRole.OPERATOR)
  admin = create_user(UserRole.ADMIN)

  response = client.get(f'/export/rae/card-index/{admin.id}/{date.today().year}', headers=auth_header(operator))

  body = response.get_json()
  assert body['status'] == 'ko'
  assert body['message'] == 'Punto vendita non trovato'


def test_export_rae_card_index_counts_each_pickup_once_with_multiple_dtr_documents(client):
  operator = create_user(UserRole.OPERATOR)
  customer, _, rae_product = _order_with_emitted_rae()
  create_dtr_document(rae_product)
  create_dtr_document(rae_product)

  response = client.get(f'/export/rae/card-index/{customer.id}/{date.today().year}', headers=auth_header(operator))

  assert response.status_code == 200
  text = ''.join(page.extract_text() for page in PdfReader(BytesIO(response.data)).pages)
  assert re.search(r'Totale pezzi:\s*(\d+)', text).group(1) == '1'


def test_export_rae_card_index_without_pickups_in_year(client):
  operator = create_user(UserRole.OPERATOR)
  customer, _, _ = _order_with_emitted_rae()

  response = client.get(f'/export/rae/card-index/{customer.id}/{date.today().year - 1}', headers=auth_header(operator))

  body = response.get_json()
  assert body['status'] == 'ko'
  assert body['message'] == 'Nessun ritiro RAEE trovato per questo punto vendita in questo anno'


def test_has_long_word_flags_only_addressees_that_would_overflow():
  assert _has_long_word('MARTIRADONNAPETRUZZELLI GIOVANNIBATTISTA') is True
  assert _has_long_word('MARTIRADONNA DONATELLA') is False
  assert _has_long_word('') is False
  assert _has_long_word(None) is False


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

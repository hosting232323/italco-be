from database_api import Session

from src.database.enum import OrderType, UserRole
from src.database.schema import Order, Product
from src.end_points.importation.pdf import (
  get_collection_point,
  normalize_city,
  pdf_create_order,
  pdf_create_product,
)

from tests.unit.factories import (
  create_collection_point,
  create_service,
  create_service_user,
  create_user,
)


SAMPLE_TEXT = """Destinatario: Mario Rossi
Via Roma 15 Città : Molfetta
Tel - Cell: 3391234567
Data consegna: 20/07/2026
"""


def test_normalize_city_applies_fixes():
  assert normalize_city('BARI-CARBONARA Bari') == 'Carbonara'
  assert normalize_city('Bari') == 'Bari'


def test_get_collection_point_returns_first_for_customer(db):
  customer = create_user(UserRole.CUSTOMER)
  collection_point = create_collection_point(customer)

  assert get_collection_point(customer.id).id == collection_point.id
  assert get_collection_point(customer.id + 999) is None


def test_pdf_create_order_extracts_fields(db):
  with Session() as session:
    order = pdf_create_order(SAMPLE_TEXT, session=session)
    session.commit()
    order_id = order.id

  from database_api.operations import get_by_id

  stored = get_by_id(Order, order_id)
  assert stored.type == OrderType.DELIVERY
  assert stored.addressee == 'Mario Rossi'
  assert 'Molfetta' in stored.address
  assert stored.cap == '70056'  # CAP di Molfetta
  assert stored.addressee_contact == '3391234567'


def test_pdf_create_product_creates_rows(db):
  from tests.unit.factories import create_order

  customer = create_user(UserRole.CUSTOMER)
  service_user = create_service_user(customer, create_service(), code='S1')
  collection_point = create_collection_point(customer)
  created_order = create_order()

  tables = [
    [
      ['Articolo', 'Modello', 'Tipologia - Descrizione', 'Quantità - Peso Jg', 'Servizio'],
      ['A1', 'MOD', 'Frigo', '1', 'S1'],
    ]
  ]

  with Session() as session:
    pdf_create_product(tables, created_order.id, collection_point.id, customer.id, session=session)
    session.commit()

  with Session() as session:
    product = session.query(Product).filter_by(order_id=created_order.id).one()
    assert product.name == 'A1 MOD Frigo'
    assert product.service_user_id == service_user.id


def test_pdf_import_endpoint_requires_files(client):
  from tests.unit.factories import auth_header

  admin = create_user(UserRole.ADMIN)

  response = client.post('/import/pdf', data={'customer_id': '1'}, headers=auth_header(admin))

  body = response.get_json()
  assert body['status'] == 'ko'
  assert body['message'] == 'Nessun file caricato'


class _FakePage:
  def __init__(self, text, tables):
    self._text = text
    self._tables = tables

  def extract_text(self):
    return self._text

  def extract_tables(self):
    return self._tables


class _FakePdf:
  def __init__(self, pages):
    self.pages = pages

  def __enter__(self):
    return self

  def __exit__(self, *_):
    return None


def test_order_import_by_pdf_creates_order_and_products(client, monkeypatch):
  from io import BytesIO

  import src.end_points.importation.pdf as pdf_module
  from tests.unit.factories import auth_header

  admin = create_user(UserRole.ADMIN)
  customer = create_user(UserRole.CUSTOMER)
  create_service_user(customer, create_service(), code='S1')
  create_collection_point(customer)

  text = 'Destinatario: Mario Rossi\nVia Roma 15 Città : Molfetta\nTel - Cell: 3391234567\nData consegna: 20/07/2026\n'
  header = ['Articolo', 'Modello', 'Tipologia - Descrizione', 'Quantità - Peso Jg', 'Servizio']
  tables = [[header, ['A1', 'M', 'Frigo', '1', 'S1']]]
  monkeypatch.setattr(pdf_module.pdfplumber, 'open', lambda file: _FakePdf([_FakePage(text, tables)]))

  response = client.post(
    '/import/pdf',
    data={'customer_id': str(customer.id), 'file': (BytesIO(b'%PDF-1.4'), 'ordine.pdf', 'application/pdf')},
    headers=auth_header(admin),
  )

  body = response.get_json()
  assert body['status'] == 'ok'
  assert body['imported_orders_count'] == 1
  from database_api import Session

  with Session() as session:
    order = session.query(Order).one()
    assert order.addressee == 'Mario Rossi'
    assert session.query(Product).filter_by(order_id=order.id).count() == 1


def test_order_import_by_pdf_rejects_unknown_collection_point(client, monkeypatch):
  from io import BytesIO

  from tests.unit.factories import auth_header

  admin = create_user(UserRole.ADMIN)
  customer = create_user(UserRole.CUSTOMER)  # nessun punto di ritiro

  response = client.post(
    '/import/pdf',
    data={'customer_id': str(customer.id), 'file': (BytesIO(b'%PDF-1.4'), 'ordine.pdf', 'application/pdf')},
    headers=auth_header(admin),
  )

  body = response.get_json()
  assert body['status'] == 'ko'
  assert body['message'] == 'Punto di ritiro non identificato'

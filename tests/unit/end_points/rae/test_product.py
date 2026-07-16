from datetime import date
from io import BytesIO

from database_api import Session
from database_api.operations import get_by_id

from src.database.enum import RaeStatus, UserRole
from src.database.schema import DtrDocument, Product, RaeProduct
from src.end_points.rae.product import (
  create_rae_product as build_rae_product,
  emit_rae_products,
  recreate_rae_products,
)

from tests.unit.factories import (
  auth_header,
  create_order,
  create_product,
  create_rae_product,
  create_rae_product_group,
  create_schedule,
  create_user,
  customer_with_service,
)


FAKE_PDF = b'%PDF-1.4\n%%EOF\n'


def test_create_rae_product_without_schedule_is_generated(db):
  customer = create_user(UserRole.CUSTOMER)
  order = create_order()
  group = create_rae_product_group()

  with Session() as session:
    rae_product = build_rae_product(2, group.id, order.id, customer.id, session=session)
    session.commit()

  assert rae_product.status == RaeStatus.GENERATED
  assert rae_product.number == 0
  assert rae_product.quantity == 2
  assert rae_product.emission_date is None


def test_create_rae_product_with_schedule_is_emitted_and_numbered(db):
  customer = create_user(UserRole.CUSTOMER)
  order = create_order()
  group = create_rae_product_group()
  schedule = create_schedule()

  with Session() as session:
    rae_product = build_rae_product(1, group.id, order.id, customer.id, session=session, schedule=schedule)
    session.commit()

  assert rae_product.status == RaeStatus.EMITTED
  assert rae_product.number == 1
  assert rae_product.dtr_date == schedule.date
  assert rae_product.emission_date is not None


def test_emit_rae_products_updates_generated_products(db):
  customer, _, service_user, _ = customer_with_service()
  order = create_order()
  group = create_rae_product_group()
  rae_product = create_rae_product(order, customer, group)
  create_product(order, service_user, rae_product_id=rae_product.id)
  schedule = create_schedule()

  with Session() as session:
    emit_rae_products(order, schedule, session=session)
    session.commit()

  refreshed = get_by_id(RaeProduct, rae_product.id)
  assert refreshed.status == RaeStatus.EMITTED
  assert refreshed.number == 1
  assert refreshed.dtr_date == schedule.date


def test_recreate_rae_products_annulls_and_relinks(db):
  customer, _, service_user, _ = customer_with_service()
  order = create_order()
  group = create_rae_product_group()
  emitted = create_rae_product(order, customer, group, status=RaeStatus.EMITTED, quantity=4)
  product = create_product(order, service_user, rae_product_id=emitted.id)

  with Session() as session:
    recreate_rae_products(order, session=session)
    session.commit()

  assert get_by_id(RaeProduct, emitted.id).status == RaeStatus.ANNULLED
  refreshed_product = get_by_id(Product, product.id)
  assert refreshed_product.rae_product_id != emitted.id
  replacement = get_by_id(RaeProduct, refreshed_product.rae_product_id)
  assert replacement.status == RaeStatus.GENERATED
  assert replacement.quantity == 4


def test_get_products_endpoint_with_filters(client):
  admin = create_user(UserRole.ADMIN)
  customer, _, _, _ = customer_with_service()
  order = create_order()
  group = create_rae_product_group()
  rae_product = create_rae_product(order, customer, group, status=RaeStatus.EMITTED, dtr_date=date.today())
  create_rae_product(create_order(), customer, group, status=RaeStatus.GENERATED)

  response = client.post(
    '/rae/product/filter',
    json={'filters': [{'model': 'RaeProduct', 'field': 'status', 'value': 'Emitted'}]},
    headers=auth_header(admin),
  )

  body = response.get_json()
  assert body['status'] == 'ok'
  assert [entry['id'] for entry in body['rae_products']] == [rae_product.id]
  assert body['rae_products'][0]['product_group']['id'] == group.id
  assert body['rae_products'][0]['order']['id'] == order.id


def test_update_product_endpoint_changes_status_and_stores_document(client, monkeypatch):
  import src.utils.storage as storage_module

  monkeypatch.setattr(storage_module, 'upload_file', lambda content, filename, folder, **kwargs: f'/fake/{filename}')
  admin = create_user(UserRole.ADMIN)
  customer = create_user(UserRole.CUSTOMER)
  order = create_order()
  rae_product = create_rae_product(order, customer)

  response = client.put(
    f'/rae/product/{rae_product.id}',
    data={
      'data': '{"status": "LDR"}',
      'document': (BytesIO(FAKE_PDF), 'dtr.pdf', 'application/pdf'),
    },
    headers=auth_header(admin),
  )

  assert response.get_json()['status'] == 'ok'
  assert get_by_id(RaeProduct, rae_product.id).status == RaeStatus.LDR
  with Session() as session:
    document = session.query(DtrDocument).filter_by(rae_product_id=rae_product.id).one()
    assert document.link.endswith(f'{document.id}.pdf')


def test_update_product_endpoint_without_document(client):
  admin = create_user(UserRole.ADMIN)
  customer = create_user(UserRole.CUSTOMER)
  order = create_order()
  rae_product = create_rae_product(order, customer)

  response = client.put(
    f'/rae/product/{rae_product.id}',
    data={'data': '{"status": "Emitted"}'},
    headers=auth_header(admin),
  )

  assert response.get_json()['status'] == 'ok'
  assert get_by_id(RaeProduct, rae_product.id).status == RaeStatus.EMITTED
  with Session() as session:
    assert session.query(DtrDocument).count() == 0

from io import BytesIO

from database_api import Session
from database_api.operations import get_by_id

from src.database.enum import RaeStatus, UserRole
from src.database.schema import Disposal, FirFirstDocument, FirFourthDocument, RaeProduct

from tests.unit.factories import (
  auth_header,
  create_carrier,
  create_collection_center,
  create_disposal,
  create_order,
  create_rae_product,
  create_rae_product_group,
  create_user,
)


FAKE_PDF = b'%PDF-1.4\n%%EOF\n'


def _fake_upload(monkeypatch):
  import src.utils.storage as storage_module

  monkeypatch.setattr(storage_module, 'upload_file', lambda content, filename, folder, **kwargs: f'/fake/{filename}')


def test_create_disposal_links_rae_products(client):
  operator = create_user(UserRole.OPERATOR)
  carrier = create_carrier()
  center = create_collection_center()
  customer = create_user(UserRole.CUSTOMER)
  rae_product = create_rae_product(create_order(), customer, status=RaeStatus.LDR)

  response = client.post(
    '/rae/disposal',
    json={
      'date': '2026-07-10',
      'code': 'SM-1',
      'carrier_id': carrier.id,
      'collection_center_id': center.id,
      'rae_product_ids': [rae_product.id],
    },
    headers=auth_header(operator),
  )

  assert response.get_json()['status'] == 'ok'
  with Session() as session:
    disposal = session.query(Disposal).one()
    refreshed = session.get(RaeProduct, rae_product.id)
    assert refreshed.disposal_id == disposal.id
    assert refreshed.status == RaeStatus.DISPOSED_OFF


def test_get_disposals_aggregates_group_quantities(client):
  operator = create_user(UserRole.OPERATOR)
  disposal = create_disposal()
  customer = create_user(UserRole.CUSTOMER)
  group_r1 = create_rae_product_group(group_code='R1')
  group_r2 = create_rae_product_group(group_code='R2')
  create_rae_product(create_order(), customer, group_r1, disposal_id=disposal.id, quantity=2)
  create_rae_product(create_order(), customer, group_r1, disposal_id=disposal.id, quantity=3)
  create_rae_product(create_order(), customer, group_r2, disposal_id=disposal.id, quantity=1)

  response = client.get('/rae/disposal', headers=auth_header(operator))

  body = response.get_json()
  assert body['status'] == 'ok'
  assert len(body['rae_disposals']) == 1
  assert body['rae_disposals'][0]['group_quantities'] == {'R1': 5, 'R2': 1}


def test_update_disposal_stores_fir_documents_and_weight(client, monkeypatch):
  _fake_upload(monkeypatch)
  operator = create_user(UserRole.OPERATOR)
  disposal = create_disposal()

  response = client.put(
    f'/rae/disposal/{disposal.id}',
    data={
      'data': '{"weight": 120.5}',
      'first_copy_document_fir': (BytesIO(FAKE_PDF), 'fir1.pdf', 'application/pdf'),
      'fourth_copy_document_fir': (BytesIO(FAKE_PDF), 'fir4.pdf', 'application/pdf'),
    },
    headers=auth_header(operator),
  )

  assert response.get_json()['status'] == 'ok'
  assert get_by_id(Disposal, disposal.id).weight == 120.5
  with Session() as session:
    assert session.query(FirFirstDocument).filter_by(disposal_id=disposal.id).count() == 1
    assert session.query(FirFourthDocument).filter_by(disposal_id=disposal.id).count() == 1


def test_update_disposal_rejects_duplicate_fir_document(client, monkeypatch):
  _fake_upload(monkeypatch)
  operator = create_user(UserRole.OPERATOR)
  disposal = create_disposal()
  from database_api.operations import create

  create(FirFirstDocument, {'disposal_id': disposal.id, 'link': '/fake/esistente.pdf'})

  response = client.put(
    f'/rae/disposal/{disposal.id}',
    data={
      'data': '{}',
      'first_copy_document_fir': (BytesIO(FAKE_PDF), 'fir1.pdf', 'application/pdf'),
    },
    headers=auth_header(operator),
  )

  # ValueError -> handler globale
  assert response.get_json()['status'] == 'ko'
  with Session() as session:
    assert session.query(FirFirstDocument).filter_by(disposal_id=disposal.id).count() == 1


def test_update_disposal_without_files_updates_weight_only(client):
  operator = create_user(UserRole.OPERATOR)
  disposal = create_disposal()

  response = client.put(
    f'/rae/disposal/{disposal.id}',
    data={'data': '{"weight": 55}'},
    headers=auth_header(operator),
  )

  assert response.get_json()['status'] == 'ok'
  assert get_by_id(Disposal, disposal.id).weight == 55
  with Session() as session:
    assert session.query(FirFirstDocument).count() == 0

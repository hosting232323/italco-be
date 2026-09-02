"""Endpoint company: dati legali stampati nei PDF e logo aziendale.

legal_name/vat_number/address/city sono sempre obbligatori in creazione; i due
campi rae_ lo diventano solo con il modulo RAEE acceso. tax_code e logo restano
opzionali. In modifica la validazione tocca solo i campi che arrivano, così un
rename non deve rispedire l'anagrafica intera.
"""

import os
import json
from io import BytesIO

from api.storage import get_full_path
from database_api.operations import get_by_id

from src import STATIC_FOLDER
from src.database.schema import Company
from src.end_points.company import LOGO_SUBFOLDER

from tests.unit.factories import auth_header, create_company, create_super_admin


FAKE_PNG = b'\x89PNG\r\n\x1a\n' + b'0' * 32

BASE_LEGAL = {
  'legal_name': 'Attività SRL',
  'vat_number': '11122233344',
  'address': 'Via Test 1',
  'city': 'Bari (BA)',
}
RAE_LEGAL = {
  'rae_registration': 'RD000S00000000 del 01/01/26',
  'rae_grouping_place': 'Via Deposito 1, Bari (BA)',
}


def _fake_upload(monkeypatch):
  from api.storage import session as storage_module

  monkeypatch.setattr(storage_module, 'upload_file', lambda content, filename, folder, **kwargs: f'/fake/{filename}')


def _create_payload(**overrides):
  return {
    'name': 'Nuova',
    'admin_email': 'admin-nuova',
    'admin_password': 'pw',
    **BASE_LEGAL,
    **overrides,
  }


def test_create_company_requires_legal_name(db, client):
  super_admin = create_super_admin()
  payload = _create_payload()
  payload.pop('legal_name')

  body = client.post('/company', json=payload, headers=auth_header(super_admin)).get_json()

  assert body['status'] == 'ko'
  assert 'Ragione sociale' in body['message']


def test_create_company_requires_vat_number(db, client):
  super_admin = create_super_admin()
  payload = _create_payload()
  payload.pop('vat_number')

  body = client.post('/company', json=payload, headers=auth_header(super_admin)).get_json()

  assert body['status'] == 'ko'
  assert 'Partita IVA' in body['message']


def test_create_company_with_rae_requires_rae_legal_fields(db, client):
  super_admin = create_super_admin()

  body = client.post('/company', json=_create_payload(rae=True), headers=auth_header(super_admin)).get_json()

  assert body['status'] == 'ko'
  assert 'Luogo di raggruppamento RAEE' in body['message']


def test_create_company_persists_legal_fields_with_optional_tax_code_empty(db, client):
  super_admin = create_super_admin()

  body = client.post('/company', json=_create_payload(), headers=auth_header(super_admin)).get_json()

  assert body['status'] == 'ok'
  company = get_by_id(Company, body['company']['id'])
  assert company.legal_name == 'Attività SRL'
  assert company.address == 'Via Test 1'
  assert company.city == 'Bari (BA)'
  assert company.tax_code is None


def test_create_company_with_rae_and_full_legal_data(db, client):
  super_admin = create_super_admin()

  body = client.post(
    '/company',
    json=_create_payload(rae=True, tax_code='02735550747', **RAE_LEGAL),
    headers=auth_header(super_admin),
  ).get_json()

  assert body['status'] == 'ok'
  company = get_by_id(Company, body['company']['id'])
  assert company.tax_code == '02735550747'
  assert company.rae_registration == 'RD000S00000000 del 01/01/26'
  assert company.rae_grouping_place == 'Via Deposito 1, Bari (BA)'


def test_create_company_stores_logo(db, client, monkeypatch):
  _fake_upload(monkeypatch)
  super_admin = create_super_admin()

  response = client.post(
    '/company',
    data={
      'data': json.dumps(_create_payload()),
      'logo': (BytesIO(FAKE_PNG), 'logo.png', 'image/png'),
    },
    headers=auth_header(super_admin),
  )

  body = response.get_json()
  assert body['status'] == 'ok'
  company = get_by_id(Company, body['company']['id'])
  assert company.logo.endswith(f'{company.id}.png')
  assert '/company/logo/' in company.logo


def test_serve_company_logo_returns_the_file(db, client):
  super_admin = create_super_admin()
  folder = get_full_path(STATIC_FOLDER, LOGO_SUBFOLDER)
  os.makedirs(folder, exist_ok=True)
  with open(os.path.join(folder, 'served.png'), 'wb') as logo_file:
    logo_file.write(FAKE_PNG)

  response = client.get('/company/logo/served.png', headers=auth_header(super_admin))

  assert response.status_code == 200
  assert response.data == FAKE_PNG


def test_update_company_updates_legal_fields(db, client):
  super_admin = create_super_admin()
  company = create_company()

  body = client.put(
    f'/company/{company.id}',
    json={'name': company.name, 'legal_name': 'Rinominata SRL', 'address': 'Via Nuova 9', 'city': 'Lecce (LE)'},
    headers=auth_header(super_admin),
  ).get_json()

  assert body['status'] == 'ok'
  refreshed = get_by_id(Company, company.id)
  assert refreshed.legal_name == 'Rinominata SRL'
  assert refreshed.city == 'Lecce (LE)'


def test_update_company_name_only_keeps_legal_fields(db, client):
  super_admin = create_super_admin()

  body = client.put(f'/company/{db.id}', json={'name': 'Solo nome nuovo'}, headers=auth_header(super_admin)).get_json()

  assert body['status'] == 'ok'
  refreshed = get_by_id(Company, db.id)
  assert refreshed.name == 'Solo nome nuovo'
  assert refreshed.legal_name == 'Test Company SRL'


def test_update_company_rejects_clearing_a_required_legal_field(db, client):
  super_admin = create_super_admin()

  body = client.put(
    f'/company/{db.id}', json={'name': db.name, 'legal_name': ''}, headers=auth_header(super_admin)
  ).get_json()

  assert body['status'] == 'ko'
  assert 'Ragione sociale' in body['message']

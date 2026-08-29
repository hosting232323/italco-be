"""Modulo RAEE per attività: interruttore, endpoint chiusi, ritiri rifiutati.

Il frontend nasconde le pagine, ma è qui che il flag diventa un vincolo: se
saltano questi test un'attività senza RAEE può comunque leggere anagrafiche e
generare ritiri chiamando gli endpoint a mano.
"""

import pytest
from api.users.security import hash_password

from database_api import Session, scope
from database_api.operations import update

from src.database.enum import UserRole
from src.database.queries import is_rae_enabled
from src.database.schema import Company, RaeProduct
from src.end_points.orders.services import create_products

from tests.unit.factories import (
  auth_header,
  create_company,
  create_order,
  create_rae_product_group,
  create_super_admin,
  create_user,
  customer_with_service,
)


RAE_OFF_MESSAGE = 'Modulo RAEE non attivo per questa attività'

# Dati legali obbligatori in creazione: legal_name/vat_number/address/city
# sempre, i due campi rae_ solo quando l'attività nasce con il modulo acceso.
LEGAL_PAYLOAD = {
  'legal_name': 'Attività SRL',
  'vat_number': '11122233344',
  'address': 'Via Test 1',
  'city': 'Bari (BA)',
  'rae_registration': 'RD000S00000000 del 01/01/26',
  'rae_grouping_place': 'Via Deposito 1, Bari (BA)',
}


@pytest.fixture
def rae_off(db) -> Company:
  """Spegne il modulo sulla company della suite, che nasce accesa."""
  return update(db, {'rae': False})


def test_new_company_starts_without_the_module(db):
  assert create_company().rae is False


def test_super_admin_creates_a_company_with_the_module_on(db, client):
  super_admin = create_super_admin()

  body = client.post(
    '/company',
    json={
      'name': 'Con RAEE',
      'admin_nickname': 'admin-rae',
      'admin_password': 'pw',
      'rae': True,
      **LEGAL_PAYLOAD,
    },
    headers=auth_header(super_admin),
  ).get_json()

  assert body['status'] == 'ok'
  assert body['company']['rae'] is True


def test_company_created_without_the_flag_has_it_off(db, client):
  super_admin = create_super_admin()

  body = client.post(
    '/company',
    json={
      'name': 'Senza RAEE',
      'admin_nickname': 'admin-no-rae',
      'admin_password': 'pw',
      'legal_name': 'Attività SRL',
      'vat_number': '11122233344',
      'address': 'Via Test 1',
      'city': 'Bari (BA)',
    },
    headers=auth_header(super_admin),
  ).get_json()

  assert body['company'].get('rae', False) is False


def test_super_admin_switches_the_module(db, client):
  super_admin = create_super_admin()
  company = create_company()

  turned_on = client.put(
    f'/company/{company.id}', json={'name': company.name, 'rae': True}, headers=auth_header(super_admin)
  ).get_json()
  companies = client.get('/company', headers=auth_header(super_admin)).get_json()['companies']
  persisted_company = next(item for item in companies if item['id'] == company.id)
  turned_off = client.put(
    f'/company/{company.id}', json={'name': company.name, 'rae': False}, headers=auth_header(super_admin)
  ).get_json()

  assert turned_on['company']['rae'] is True
  assert persisted_company['rae'] is True
  assert turned_off['company'].get('rae', False) is False


def test_updating_only_the_company_name_preserves_the_module(db, client):
  super_admin = create_super_admin()

  body = client.put(f'/company/{db.id}', json={'name': 'Nuovo nome'}, headers=auth_header(super_admin)).get_json()

  assert body['status'] == 'ok'
  assert body['company']['name'] == 'Nuovo nome'
  assert body['company']['rae'] is True


def test_company_update_rejects_a_non_boolean_module_flag(db, client):
  super_admin = create_super_admin()

  body = client.put(
    f'/company/{db.id}', json={'name': db.name, 'rae': 'false'}, headers=auth_header(super_admin)
  ).get_json()

  assert body['status'] == 'ko'
  assert body['message'] == 'Il flag RAEE deve essere booleano'
  assert db.rae is True


def test_admin_cannot_switch_the_module(db, client):
  """Il flag è del super admin: l'admin della company non se lo accende da solo."""
  admin = create_user(UserRole.ADMIN)

  body = client.put(f'/company/{db.id}', json={'name': db.name, 'rae': True}, headers=auth_header(admin)).get_json()

  assert body['status'] == 'forbidden'
  assert body['message'] == 'Ruolo non autorizzato'


def test_login_carries_the_flag_to_the_frontend(db, client):
  """È il campo su cui il menù decide se mostrare le pagine RAEE."""
  create_user(UserRole.ADMIN, nickname='login-rae', password=hash_password('pw'))

  body = client.post('/user/login', json={'email': 'login-rae', 'password': 'pw'}).get_json()

  assert body['company']['rae'] is True


@pytest.mark.parametrize(
  'method, path',
  [
    ('get', '/rae/product-group'),
    ('post', '/rae/product-group'),
    ('post', '/rae/product/filter'),
    ('get', '/rae/carrier'),
    ('get', '/rae/collection-center'),
    ('get', '/rae/disposal'),
    ('post', '/rae/disposal'),
    ('get', '/export/rae/1'),
    ('get', '/export/rae/product/1'),
    ('get', '/export/disposal/1/attached-1'),
  ],
)
def test_rae_endpoints_are_closed_without_the_module(rae_off, client, method, path):
  admin = create_user(UserRole.ADMIN)

  body = getattr(client, method)(path, json={'filters': {}}, headers=auth_header(admin)).get_json()

  assert body['status'] == 'ko'
  assert body['message'] == RAE_OFF_MESSAGE


def test_rae_endpoints_stay_open_with_the_module(db, client):
  admin = create_user(UserRole.ADMIN)

  body = client.get('/rae/product-group', headers=auth_header(admin)).get_json()

  assert body['status'] == 'ok'


def test_super_admin_is_bound_to_the_module_of_the_selected_company(db, client):
  """Il super admin scavalca il ruolo, non il modulo: quello è dell'attività."""
  super_admin = create_super_admin()
  without_rae = create_company()

  body = client.get('/rae/product-group', headers=auth_header(super_admin, without_rae.id)).get_json()

  assert body['status'] == 'ko'
  assert body['message'] == RAE_OFF_MESSAGE


def test_rae_withdraw_is_refused_on_the_order_form(rae_off, db):
  """Il bottone sparisce dal form, ma il payload può arrivare lo stesso."""
  customer, service, _, collection_point = customer_with_service()
  group = create_rae_product_group()
  order = create_order()
  payload = {
    'Lavatrice': {
      'services': [{'id': service.id}],
      'collection_point': {'id': collection_point.id},
      'rae_product': {'quantity': 1, 'rae_product_group_id': group.id},
    }
  }

  with pytest.raises(Exception, match='Il modulo RAEE non è attivo'):
    with Session() as session:
      create_products(order, payload, customer.id, False, session=session)
      session.commit()

  with Session() as session:
    assert session.query(RaeProduct).count() == 0


def test_is_rae_enabled_reads_the_active_company(db):
  without_rae = create_company()

  with scope(company_id=without_rae.id):
    assert is_rae_enabled() is False

  assert is_rae_enabled() is True


def test_is_rae_enabled_without_active_company(db):
  with scope(company_id=None):
    assert is_rae_enabled() is False

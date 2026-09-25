"""Pianificazione automatica degli ordini per attività: interruttore, endpoint chiuso.

Il frontend nasconde il bottone nella pagina Ordini, ma è qui che il flag
diventa un vincolo: senza, un'attività può comunque chiedere le proposte di
schedulazione chiamando l'endpoint a mano.
"""

import pytest
from api.users.security import hash_password

from database_api import Session, scope
from database_api.operations import update

from src.database.enum import UserRole
from src.database.queries import is_automatic_planning_enabled
from src.database.schema import User

from tests.unit.factories import (
  auth_header,
  create_company,
  create_super_admin,
  create_transport,
  create_user,
)


def _user_by_nickname(nickname: str) -> User:
  with Session() as session:
    return session.query(User).filter(User.nickname == nickname).one()


PLANNING_OFF_MESSAGE = 'Pianificazione automatica non attiva per questa attività'

SUGGESTIONS_PATH = '/schedule/suggestions?work_date=2026-07-15&min_size_group=1&max_size_group=5&max_distance_km=10'

# Dati legali obbligatori in creazione, indipendenti dal RAEE.
LEGAL_PAYLOAD = {
  'legal_name': 'Attività SRL',
  'vat_number': '11122233344',
  'address': 'Via Test 1',
  'city': 'Bari (BA)',
}


@pytest.fixture
def planning_off(db):
  """Spegne il flag sulla company della suite, che nasce accesa."""
  return update(db, {'automatic_planning': False})


def test_new_company_starts_without_automatic_planning(db):
  assert create_company().automatic_planning is False


def test_super_admin_creates_a_company_with_automatic_planning_on(db, client):
  super_admin = create_super_admin()

  body = client.post(
    '/company',
    json={
      'name': 'Con pianificazione',
      'admin_nickname': 'admin-planning',
      'admin_password': 'pw',
      'automatic_planning': True,
      **LEGAL_PAYLOAD,
    },
    headers=auth_header(super_admin),
  ).get_json()

  assert body['status'] == 'ok'
  assert body['company']['automatic_planning'] is True


def test_company_created_without_the_flag_has_it_off(db, client):
  super_admin = create_super_admin()

  body = client.post(
    '/company',
    json={
      'name': 'Senza pianificazione',
      'admin_nickname': 'admin-no-planning',
      'admin_password': 'pw',
      **LEGAL_PAYLOAD,
    },
    headers=auth_header(super_admin),
  ).get_json()

  assert body['company'].get('automatic_planning', False) is False


def test_super_admin_switches_the_flag(db, client):
  super_admin = create_super_admin()
  company = create_company()

  turned_on = client.put(
    f'/company/{company.id}',
    json={'name': company.name, 'automatic_planning': True},
    headers=auth_header(super_admin),
  ).get_json()
  companies = client.get('/company', headers=auth_header(super_admin)).get_json()['companies']
  persisted_company = next(item for item in companies if item['id'] == company.id)
  turned_off = client.put(
    f'/company/{company.id}',
    json={'name': company.name, 'automatic_planning': False},
    headers=auth_header(super_admin),
  ).get_json()

  assert turned_on['company']['automatic_planning'] is True
  assert persisted_company['automatic_planning'] is True
  assert turned_off['company'].get('automatic_planning', False) is False


def test_updating_only_the_company_name_preserves_the_flag(db, client):
  super_admin = create_super_admin()

  body = client.put(f'/company/{db.id}', json={'name': 'Nuovo nome'}, headers=auth_header(super_admin)).get_json()

  assert body['status'] == 'ok'
  assert body['company']['name'] == 'Nuovo nome'
  assert body['company']['automatic_planning'] is True


def test_company_update_rejects_a_non_boolean_flag(db, client):
  super_admin = create_super_admin()

  body = client.put(
    f'/company/{db.id}',
    json={'name': db.name, 'automatic_planning': 'false'},
    headers=auth_header(super_admin),
  ).get_json()

  assert body['status'] == 'ko'
  assert body['message'] == 'Il flag di pianificazione automatica deve essere booleano'
  assert db.automatic_planning is True


def test_admin_cannot_switch_the_flag(db, client):
  """Il flag è del super admin: l'admin della company non se lo accende da solo."""
  admin = create_user(UserRole.ADMIN)

  body = client.put(
    f'/company/{db.id}', json={'name': db.name, 'automatic_planning': True}, headers=auth_header(admin)
  ).get_json()

  assert body['status'] == 'forbidden'
  assert body['message'] == 'Ruolo non autorizzato'


def test_login_carries_the_flag_to_the_frontend(db, client):
  """È il campo su cui la pagina Ordini decide se mostrare il bottone."""
  create_user(UserRole.ADMIN, nickname='login-planning', password=hash_password('pw'))

  body = client.post('/user/login', json={'email': 'login-planning', 'password': 'pw'}).get_json()

  assert body['company']['automatic_planning'] is True


def test_suggestions_endpoint_is_closed_without_the_flag(planning_off, client):
  admin = create_user(UserRole.ADMIN)

  body = client.get(SUGGESTIONS_PATH, headers=auth_header(admin)).get_json()

  assert body['status'] == 'ko'
  assert body['message'] == PLANNING_OFF_MESSAGE


def test_super_admin_is_bound_to_the_flag_of_the_selected_company(db, client):
  """Il super admin scavalca il ruolo, non il flag: quello è dell'attività."""
  super_admin = create_super_admin()
  without_planning = create_company()

  body = client.get(SUGGESTIONS_PATH, headers=auth_header(super_admin, without_planning.id)).get_json()

  assert body['status'] == 'ko'
  assert body['message'] == PLANNING_OFF_MESSAGE


def test_is_automatic_planning_enabled_reads_the_active_company(db):
  without_planning = create_company()

  with scope(company_id=without_planning.id):
    assert is_automatic_planning_enabled() is False

  assert is_automatic_planning_enabled() is True


def test_is_automatic_planning_enabled_without_active_company(db):
  with scope(company_id=None):
    assert is_automatic_planning_enabled() is False


# --- Flag per punto vendita (User con role Customer) ---------------------
# Granularità più fine dello stesso interruttore: un'attività può avere la
# pianificazione automatica accesa ma un singolo punto vendita spenta.


def test_new_customer_starts_with_automatic_planning_on(db):
  """Nasce true: se l'attività accende il flag, il punto vendita è già pronto."""
  assert create_user(UserRole.CUSTOMER).automatic_planning is True


def test_admin_can_switch_off_a_customer_automatic_planning(db, client):
  admin = create_user(UserRole.ADMIN)

  body = client.post(
    '/user',
    json={'nickname': 'punto-vendita-off', 'password': 'pw', 'role': 'Customer', 'automatic_planning': False},
    headers=auth_header(admin),
  ).get_json()

  assert body['status'] == 'ok'
  assert _user_by_nickname('punto-vendita-off').automatic_planning is False


def test_create_user_ignores_the_flag_for_non_customer_roles(db, client):
  admin = create_user(UserRole.ADMIN)

  body = client.post(
    '/user',
    json={'nickname': 'operatore-flag', 'password': 'pw', 'role': 'Operator', 'automatic_planning': False},
    headers=auth_header(admin),
  ).get_json()

  assert body['status'] == 'ok'
  assert _user_by_nickname('operatore-flag').automatic_planning is True


def test_create_user_ignores_the_flag_when_company_automatic_planning_is_off(planning_off, client):
  admin = create_user(UserRole.ADMIN)

  body = client.post(
    '/user',
    json={'nickname': 'punto-vendita-no-azienda', 'password': 'pw', 'role': 'Customer', 'automatic_planning': False},
    headers=auth_header(admin),
  ).get_json()

  assert body['status'] == 'ok'
  assert _user_by_nickname('punto-vendita-no-azienda').automatic_planning is True


def test_admin_updates_an_existing_customer_automatic_planning(db, client):
  admin = create_user(UserRole.ADMIN)
  customer = create_user(UserRole.CUSTOMER)

  body = client.put(f'/user/{customer.id}', json={'automatic_planning': False}, headers=auth_header(admin)).get_json()

  assert body['status'] == 'ok'
  assert body['user']['automatic_planning'] is False


def test_update_user_rejects_without_company_automatic_planning(planning_off, client):
  admin = create_user(UserRole.ADMIN)
  customer = create_user(UserRole.CUSTOMER)

  body = client.put(f'/user/{customer.id}', json={'automatic_planning': True}, headers=auth_header(admin)).get_json()

  assert body['status'] == 'ko'
  assert customer.automatic_planning is True


def test_update_user_rejects_for_non_customer_roles(db, client):
  admin = create_user(UserRole.ADMIN)
  delivery = create_user(UserRole.DELIVERY)

  body = client.put(f'/user/{delivery.id}', json={'automatic_planning': False}, headers=auth_header(admin)).get_json()

  assert body['status'] == 'ko'


def test_update_user_rejects_missing_field(db, client):
  admin = create_user(UserRole.ADMIN)
  customer = create_user(UserRole.CUSTOMER)

  body = client.put(f'/user/{customer.id}', json={}, headers=auth_header(admin)).get_json()

  assert body['status'] == 'ko'


def test_login_carries_the_customer_flag_to_the_frontend(db, client):
  create_user(UserRole.CUSTOMER, nickname='login-punto-vendita', password=hash_password('pw'), automatic_planning=False)

  body = client.post('/user/login', json={'email': 'login-punto-vendita', 'password': 'pw'}).get_json()

  assert body['automatic_planning'] is False


def test_delivery_coverage_endpoints_closed_without_the_flag(planning_off, client):
  admin = create_user(UserRole.ADMIN)
  transport = create_transport()

  get_response = client.get('/delivery-coverage', headers=auth_header(admin)).get_json()
  post_response = client.post(
    '/delivery-coverage',
    json={
      'day_of_week': 0,
      'transport_id': transport.id,
      'start_time': '08:00',
      'end_time': '18:00',
      'caps': ['70051'],
    },
    headers=auth_header(admin),
  ).get_json()

  assert get_response['status'] == 'ko'
  assert get_response['message'] == PLANNING_OFF_MESSAGE
  assert post_response['status'] == 'ko'
  assert post_response['message'] == PLANNING_OFF_MESSAGE

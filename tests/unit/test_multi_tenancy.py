"""Isolamento fra company: filtro in lettura, timbro in scrittura, super admin.

Sono i test che tengono in piedi la feature: se saltano questi, i dati di un
cliente finiscono sotto gli occhi di un altro.
"""

import jwt
import pytest

from database_api import scope
from database_api.operations import get_all

from src.database.enum import UserRole
from src.database.schema import Order, Service
from src.end_points.users.session import DECODE_JWT_TOKEN

from tests.unit.factories import (
  auth_header,
  create_company,
  create_order,
  create_service,
  create_super_admin,
  create_user,
)


def test_read_only_returns_the_active_company(db):
  mine = create_order()
  other = create_company()
  with scope(company_id=other.id):
    theirs = create_order()

  ids = [order.id for order in get_all(Order)]

  assert mine.id in ids
  assert theirs.id not in ids


def test_read_without_active_company_sees_everything(db):
  mine = create_order()
  other = create_company()
  with scope(company_id=other.id):
    theirs = create_order()

  with scope(company_id=None):
    ids = [order.id for order in get_all(Order)]

  assert {mine.id, theirs.id} <= set(ids)


def test_write_is_stamped_with_the_active_company(db):
  service: Service = create_service()

  assert service.company_id == db.id


def test_write_without_active_company_is_refused(db):
  with scope(company_id=None), pytest.raises(RuntimeError, match='Nessuna company attiva'):
    create_service()


def test_super_admin_has_no_company(db):
  assert create_super_admin().company_id is None


def test_join_does_not_leak_other_companies(db, client):
  """Il filtro copre gli alias: un outerjoin non deve essere una scorciatoia."""
  admin = create_user(UserRole.ADMIN)
  mine = create_service()
  other = create_company()
  with scope(company_id=other.id):
    theirs = create_service()

  ids = [service['id'] for service in client.get('/service', headers=auth_header(admin)).get_json()['services']]

  assert mine.id in ids
  assert theirs.id not in ids


def test_wrong_role_is_not_reported_as_expired_session(db, client):
  """Il frontend fa logout su status 'session': un ruolo negato deve fermare la
  chiamata, non la sessione."""
  customer = create_user(UserRole.CUSTOMER)

  body = client.get('/user', headers=auth_header(customer)).get_json()

  assert body['status'] == 'ko'
  assert body['message'] == 'Ruolo non autorizzato'


def test_company_endpoints_are_reserved_to_super_admin(db, client):
  admin = create_user(UserRole.ADMIN)

  body = client.get('/company', headers=auth_header(admin)).get_json()

  assert body['status'] == 'ko'
  assert body['message'] == 'Ruolo non autorizzato'


def test_super_admin_without_selection_is_blocked(db, client):
  super_admin = create_super_admin()

  body = client.get('/user', headers=auth_header(super_admin)).get_json()

  assert body['status'] == 'ko'
  assert body['message'] == 'Nessuna company selezionata'


def test_super_admin_sees_the_company_it_selected(db, client):
  mine = create_user(UserRole.CUSTOMER)
  other = create_company()
  with scope(company_id=other.id):
    theirs = create_user(UserRole.CUSTOMER)
  super_admin = create_super_admin()

  body = client.get('/user', headers=auth_header(super_admin, other.id)).get_json()

  nicknames = [user['nickname'] for user in body['users']]
  assert theirs.nickname in nicknames
  assert mine.nickname not in nicknames


def test_select_company_returns_a_token_carrying_it(db, client):
  super_admin = create_super_admin()
  other = create_company()

  body = client.post('/company/select', json={'company_id': other.id}, headers=auth_header(super_admin)).get_json()

  assert body['status'] == 'ok'
  assert body['company']['id'] == other.id
  # Il token riemesso è quello della selezione, non quello dello scope precedente.
  assert client.get('/user', headers={'Authorization': body['new_token']}).get_json()['status'] == 'ok'


def test_select_unknown_company_is_refused(db, client):
  super_admin = create_super_admin()

  body = client.post('/company/select', json={'company_id': 9999}, headers=auth_header(super_admin)).get_json()

  assert body['status'] == 'ko'
  assert body['message'] == 'Company non trovata'


def test_select_none_clears_the_selection(db, client):
  super_admin = create_super_admin()
  other = create_company()

  body = client.post(
    '/company/select', json={'company_id': None}, headers=auth_header(super_admin, other.id)
  ).get_json()

  assert body['company'] is None
  assert client.get('/user', headers={'Authorization': body['new_token']}).get_json()['message'] == (
    'Nessuna company selezionata'
  )


def test_normal_user_cannot_move_to_another_company_with_the_token(db, client):
  """Il claim della company vale solo per il super admin: per tutti gli altri lo
  scope viene riletto dall'utente, non dal token."""
  admin = create_user(UserRole.ADMIN)
  other = create_company()
  with scope(company_id=other.id):
    theirs = create_user(UserRole.CUSTOMER)

  body = client.get('/user', headers=auth_header(admin, other.id)).get_json()

  assert theirs.nickname not in [user['nickname'] for user in body['users']]


def test_refreshed_token_keeps_the_selected_company(db, client):
  super_admin = create_super_admin()
  other = create_company()

  body = client.get('/user', headers=auth_header(super_admin, other.id)).get_json()

  assert jwt.decode(body['new_token'], DECODE_JWT_TOKEN, algorithms=['HS256'])['company_id'] == other.id


def test_login_returns_the_company_of_the_user(db, client):
  create_user(UserRole.ADMIN, nickname='login-admin', password='pw')

  body = client.post('/user/login', json={'email': 'login-admin', 'password': 'pw'}).get_json()

  assert body['status'] == 'ok'
  assert body['company']['id'] == db.id


def test_login_of_super_admin_has_no_company(db, client):
  create_super_admin(nickname='login-super', password='pw')

  body = client.post('/user/login', json={'email': 'login-super', 'password': 'pw'}).get_json()

  assert body['status'] == 'ok'
  assert body['company'] is None

"""Passaggio di un ordine a un'altra company: ricollegamento per Ragione Sociale e nome servizio."""

import pytest
from database_api import scope
from database_api.operations import create, get_by_id, update

from src.database.enum import OrderStatus, OrderType, UserRole
from src.database.schema import History, Order, Photo, Product, ServiceUser

from tests.unit.factories import (
  auth_header,
  create_collection_point,
  create_company,
  create_customer_info,
  create_order,
  create_product,
  create_rae_product,
  create_schedule,
  create_service,
  create_service_user,
  create_super_admin,
  create_transport,
  create_user,
  link_order_to_schedule,
)

RAGIONE_SOCIALE = 'Expert Srl'
SERVICE_NAME = '172637 Consegna al piano Frigo'
POINT = {'name': 'Negozio', 'address': 'Via Toscanini 20, Bari'}


def build_customer(company, nickname, ragione_sociale=RAGIONE_SOCIALE, service_name=SERVICE_NAME, with_point=True):
  """Cliente con scheda anagrafica, servizio e punto di ritiro dentro la company."""
  with scope(company_id=company.id):
    customer = create_user(UserRole.CUSTOMER, nickname=nickname)
    create_customer_info(customer, company_name=ragione_sociale)
    service_user = (
      create_service_user(customer, create_service(OrderType.DELIVERY, name=service_name)) if service_name else None
    )
    point = create_collection_point(customer, **POINT) if with_point else None
  return customer, service_user, point


def build_order(company, service_user, point):
  with scope(company_id=company.id):
    order = create_order()
    product = create_product(order, service_user, collection_point_id=point.id)
    return order, product


def move_headers(company):
  return auth_header(create_super_admin(), company.id)


def post(client, company, order, path='', **body):
  return client.post(f'/order/{order.id}/company{path}', json=body, headers=move_headers(company)).get_json()


def row(model, row_id):
  with scope(company_id=None):
    return get_by_id(model, row_id)


def test_move_relinks_customer_service_and_collection_point(db, client):
  target = create_company()
  _, source_su, source_point = build_customer(db, 'expert-mallardo')
  target_customer, target_su, target_point = build_customer(target, 'expert-japigia')
  order, product = build_order(db, source_su, source_point)
  with scope(company_id=db.id):
    history = create(History, {'order_id': order.id, 'status': {'type': 'status', 'value': 'Acquired'}})
    photo = create(Photo, {'order_id': order.id, 'link': 'photos/a.jpg'})

  body = post(client, db, order, company_id=target.id)

  assert body['status'] == 'ok'
  assert row(Order, order.id).company_id == target.id
  moved = row(Product, product.id)
  assert moved.company_id == target.id
  assert moved.service_user_id == target_su.id
  assert moved.collection_point_id == target_point.id
  assert row(History, history.id).company_id == target.id
  assert row(Photo, photo.id).company_id == target.id
  assert row(ServiceUser, target_su.id).user_id == target_customer.id


def test_preview_does_not_write(db, client):
  target = create_company()
  _, source_su, source_point = build_customer(db, 'a')
  _, target_su, target_point = build_customer(target, 'b')
  order, product = build_order(db, source_su, source_point)

  body = post(client, db, order, '/preview', company_id=target.id)

  assert body['status'] == 'ok'
  assert body['plan']['errors'] == []
  assert body['plan']['target_user']['nickname'] == 'b'
  assert body['plan']['services'][0]['target_service_user_id'] == target_su.id
  assert row(Order, order.id).company_id == db.id
  assert row(Product, product.id).service_user_id == source_su.id


def test_match_ignores_case_and_extra_spaces(db, client):
  target = create_company()
  _, source_su, source_point = build_customer(db, 'a', ragione_sociale='Expert  SRL ')
  build_customer(target, 'b', ragione_sociale='expert srl', service_name='172637  consegna al piano frigo')
  order, _ = build_order(db, source_su, source_point)

  assert post(client, db, order, company_id=target.id)['status'] == 'ok'


def test_missing_service_blocks_and_leaves_order_untouched(db, client):
  target = create_company()
  _, source_su, source_point = build_customer(db, 'a')
  build_customer(target, 'b', service_name='Altro servizio')
  order, product = build_order(db, source_su, source_point)

  body = post(client, db, order, company_id=target.id)

  assert body['status'] == 'ko'
  assert SERVICE_NAME in body['message']
  assert row(Order, order.id).company_id == db.id
  assert row(Product, product.id).service_user_id == source_su.id


def test_missing_collection_point_blocks(db, client):
  target = create_company()
  _, source_su, source_point = build_customer(db, 'a')
  build_customer(target, 'b', with_point=False)
  order, _ = build_order(db, source_su, source_point)

  body = post(client, db, order, company_id=target.id)

  assert body['status'] == 'ko'
  assert 'Punto di ritiro' in body['message']


def test_unknown_ragione_sociale_blocks(db, client):
  target = create_company()
  _, source_su, source_point = build_customer(db, 'a')
  build_customer(target, 'b', ragione_sociale='Altra Srl')
  order, _ = build_order(db, source_su, source_point)

  body = post(client, db, order, company_id=target.id)

  assert body['status'] == 'ko'
  assert RAGIONE_SOCIALE in body['message']


def test_source_customer_without_ragione_sociale_blocks(db, client):
  target = create_company()
  _, source_su, source_point = build_customer(db, 'a', ragione_sociale=None)
  build_customer(target, 'b')
  order, _ = build_order(db, source_su, source_point)

  body = post(client, db, order, company_id=target.id)

  assert body['status'] == 'ko'
  assert 'Ragione Sociale' in body['message']


def test_ambiguous_ragione_sociale_needs_explicit_customer(db, client):
  target = create_company()
  _, source_su, source_point = build_customer(db, 'a')
  first, _, _ = build_customer(target, 'b1')
  second, second_su, second_point = build_customer(target, 'b2')
  order, product = build_order(db, source_su, source_point)

  preview = post(client, db, order, '/preview', company_id=target.id)
  assert {user['id'] for user in preview['plan']['target_users']} == {first.id, second.id}
  assert post(client, db, order, company_id=target.id)['status'] == 'ko'

  body = post(client, db, order, company_id=target.id, user_id=second.id)

  assert body['status'] == 'ok'
  assert row(Product, product.id).service_user_id == second_su.id
  assert row(Product, product.id).collection_point_id == second_point.id


def test_explicit_customer_must_belong_to_target_company(db, client):
  target = create_company()
  _, source_su, source_point = build_customer(db, 'a')
  build_customer(target, 'b')
  order, _ = build_order(db, source_su, source_point)
  stranger, _, _ = build_customer(db, 'stranger')

  body = post(client, db, order, company_id=target.id, user_id=stranger.id)

  assert body['status'] == 'ko'
  assert 'non appartiene' in body['message']


def test_booked_order_can_be_moved(db, client):
  target = create_company()
  _, source_su, source_point = build_customer(db, 'a')
  build_customer(target, 'b')
  order, _ = build_order(db, source_su, source_point)
  with scope(company_id=db.id):
    update(order, {'status': OrderStatus.BOOKED})

  assert post(client, db, order, company_id=target.id)['status'] == 'ok'


@pytest.mark.parametrize(
  'status',
  [
    OrderStatus.SCHEDULED,
    OrderStatus.BOOKING,
    OrderStatus.DELIVERED,
    OrderStatus.NOT_DELIVERED,
    OrderStatus.TO_RESCHEDULE,
  ],
)
def test_order_past_booked_is_not_moved(db, client, status):
  target = create_company()
  _, source_su, source_point = build_customer(db, 'a')
  build_customer(target, 'b')
  order, _ = build_order(db, source_su, source_point)
  with scope(company_id=db.id):
    update(order, {'status': status})

  body = post(client, db, order, company_id=target.id)

  assert body['status'] == 'ko'
  assert 'Acquisito o Prenotato' in body['message']
  assert row(Order, order.id).company_id == db.id


def test_order_in_a_schedule_is_not_moved(db, client):
  target = create_company()
  _, source_su, source_point = build_customer(db, 'a')
  build_customer(target, 'b')
  order, _ = build_order(db, source_su, source_point)
  with scope(company_id=db.id):
    link_order_to_schedule(order, create_schedule())

  body = post(client, db, order, company_id=target.id)

  assert body['status'] == 'ko'
  assert 'borderò' in body['message']
  assert row(Order, order.id).company_id == db.id


def test_order_with_rae_is_not_moved(db, client):
  target = create_company()
  customer, source_su, source_point = build_customer(db, 'a')
  build_customer(target, 'b')
  order, _ = build_order(db, source_su, source_point)
  with scope(company_id=db.id):
    create_rae_product(order, customer)

  body = post(client, db, order, company_id=target.id)

  assert body['status'] == 'ko'
  assert 'RAEE' in body['message']


def test_order_with_assigned_vehicle_is_not_moved(db, client):
  target = create_company()
  _, source_su, source_point = build_customer(db, 'a')
  build_customer(target, 'b')
  order, product = build_order(db, source_su, source_point)
  with scope(company_id=db.id):
    update(product, {'transport_id': create_transport().id})

  body = post(client, db, order, company_id=target.id)

  assert body['status'] == 'ko'
  assert 'veicolo' in body['message']


def test_same_or_unknown_company_is_refused(db, client):
  _, source_su, source_point = build_customer(db, 'a')
  order, _ = build_order(db, source_su, source_point)

  assert 'già' in post(client, db, order, company_id=db.id)['message']
  assert 'non trovata' in post(client, db, order, company_id=99999)['message']


def test_order_of_another_company_cannot_be_moved(db, client):
  """Si opera sulla company selezionata: un ordine altrui è come se non esistesse."""
  target = create_company()
  _, target_su, target_point = build_customer(target, 'b')
  order, _ = build_order(target, target_su, target_point)

  body = post(client, db, order, company_id=db.id)

  assert body['status'] == 'ko'
  assert row(Order, order.id).company_id == target.id


def test_admin_can_move_within_its_own_company(db, client):
  target = create_company()
  _, source_su, source_point = build_customer(db, 'a')
  build_customer(target, 'b')
  order, _ = build_order(db, source_su, source_point)
  admin = create_user(UserRole.ADMIN)

  response = client.post(f'/order/{order.id}/company', json={'company_id': target.id}, headers=auth_header(admin))

  assert response.get_json()['status'] == 'ok'
  assert row(Order, order.id).company_id == target.id


def test_admin_cannot_move_an_order_of_another_company(db, client):
  target = create_company()
  _, target_su, target_point = build_customer(target, 'b')
  order, _ = build_order(target, target_su, target_point)
  admin = create_user(UserRole.ADMIN)

  body = client.post(f'/order/{order.id}/company', json={'company_id': db.id}, headers=auth_header(admin)).get_json()

  assert body['status'] == 'ko'
  assert row(Order, order.id).company_id == target.id


@pytest.mark.parametrize('role', [UserRole.OPERATOR, UserRole.CUSTOMER, UserRole.DELIVERY])
def test_other_roles_cannot_move(db, client, role):
  target = create_company()
  _, source_su, source_point = build_customer(db, 'a')
  build_customer(target, 'b')
  order, _ = build_order(db, source_su, source_point)

  for path in ('', '/preview'):
    response = client.post(
      f'/order/{order.id}/company{path}', json={'company_id': target.id}, headers=auth_header(create_user(role))
    )
    assert response.status_code == 403
  assert client.get('/order/company-targets', headers=auth_header(create_user(role))).status_code == 403
  assert row(Order, order.id).company_id == db.id


def test_targets_list_other_companies_with_id_and_name_only(db, client):
  other = create_company('Messina')

  body = client.get('/order/company-targets', headers=auth_header(create_user(UserRole.ADMIN))).get_json()

  assert body == {'status': 'ok', 'companies': [{'id': other.id, 'name': 'Messina'}]}
  assert db.id not in [company['id'] for company in body['companies']]

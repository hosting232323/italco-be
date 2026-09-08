"""Luoghi di smaltimento RAEE: CRUD del super admin da Gestione Company, e
lettura tenant per il form di smaltimento (DisposalForm).

Il CRUD vive sotto /company/<company_id>/... perché è il super admin a
gestirlo, non necessariamente operando sulla company di cui sta configurando i
luoghi: da qui il test di scavalcamento (operare su A, gestire i luoghi di B).
"""

from database_api.operations import get_by_id

from src.database.enum import UserRole
from src.database.schema import RaeDisposalPlace
from src.end_points.rae.disposal_place import DELETE_LAST_PLACE_ERROR

from tests.unit.factories import auth_header, create_company, create_rae_disposal_place, create_super_admin, create_user


def test_create_company_disposal_place(db, client):
  super_admin = create_super_admin()

  response = client.post(
    f'/company/{db.id}/rae-disposal-place',
    json={'name': 'Deposito Bari', 'rae_grouping_place': 'Via Bari 1'},
    headers=auth_header(super_admin),
  )

  assert response.get_json()['status'] == 'ok'


def test_get_company_disposal_places(db, client):
  super_admin = create_super_admin()
  create_rae_disposal_place()  # rientra nello scope della company della fixture db

  response = client.get(f'/company/{db.id}/rae-disposal-place', headers=auth_header(super_admin))

  body = response.get_json()
  assert body['status'] == 'ok'
  # 1 dalla fixture db + 1 appena creato
  assert len(body['rae_disposal_places']) == 2


def test_update_company_disposal_place(db, client):
  super_admin = create_super_admin()
  place = create_rae_disposal_place()

  response = client.put(
    f'/company/{db.id}/rae-disposal-place/{place.id}', json={'name': 'Rinominato'}, headers=auth_header(super_admin)
  )

  assert response.get_json()['status'] == 'ok'
  assert get_by_id(RaeDisposalPlace, place.id).name == 'Rinominato'


def test_delete_company_disposal_place(db, client):
  # La fixture db lascia la company con un solo luogo: gliene serve un secondo per poter cancellare.
  super_admin = create_super_admin()
  create_rae_disposal_place()
  extra_place = create_rae_disposal_place()

  response = client.delete(f'/company/{db.id}/rae-disposal-place/{extra_place.id}', headers=auth_header(super_admin))

  assert response.get_json()['status'] == 'ok'
  assert get_by_id(RaeDisposalPlace, extra_place.id) is None


def test_delete_last_disposal_place_is_refused_while_rae_is_on(db, client):
  super_admin = create_super_admin()
  places = client.get(f'/company/{db.id}/rae-disposal-place', headers=auth_header(super_admin)).get_json()[
    'rae_disposal_places'
  ]
  assert len(places) == 1

  response = client.delete(f'/company/{db.id}/rae-disposal-place/{places[0]["id"]}', headers=auth_header(super_admin))

  body = response.get_json()
  assert body['status'] == 'ko'
  assert body['message'] == DELETE_LAST_PLACE_ERROR
  assert get_by_id(RaeDisposalPlace, places[0]['id']) is not None


def test_get_tenant_disposal_places(db, client):
  operator = create_user(UserRole.OPERATOR)

  response = client.get('/rae/disposal-place', headers=auth_header(operator))

  body = response.get_json()
  assert body['status'] == 'ok'
  assert len(body['rae_disposal_places']) == 1


def test_super_admin_manages_places_of_a_different_company_than_the_one_it_operates(db, client):
  """Il super admin 'opera come' company A ma configura i luoghi di B: lo
  scope esplicito con company_id di destinazione deve prevalere su quello
  ambientale della sessione, non venirci filtrato sopra."""
  super_admin = create_super_admin()
  other_company = create_company(rae=True)

  response = client.post(
    f'/company/{other_company.id}/rae-disposal-place',
    json={'name': 'Deposito B'},
    headers=auth_header(super_admin, db.id),
  )
  assert response.get_json()['status'] == 'ok'

  own_places = client.get(f'/company/{db.id}/rae-disposal-place', headers=auth_header(super_admin, db.id)).get_json()[
    'rae_disposal_places'
  ]
  other_places = client.get(
    f'/company/{other_company.id}/rae-disposal-place', headers=auth_header(super_admin, db.id)
  ).get_json()['rae_disposal_places']

  assert len(own_places) == 1
  assert len(other_places) == 1
  assert other_places[0]['name'] == 'Deposito B'

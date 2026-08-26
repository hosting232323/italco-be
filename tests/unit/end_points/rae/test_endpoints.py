"""Test delle route generiche di src/end_points/rae/__init__.py."""

import pytest

from src.database.enum import UserRole

from tests.unit.factories import auth_header, create_user


def query_token(role: UserRole) -> str:
  return auth_header(create_user(role))['Authorization']


def test_serve_document_requires_a_token(client):
  response = client.get('/rae/dtr-documents/1.pdf')

  body = response.get_json()
  assert body['status'] == 'session'
  assert body['message'] == 'Token assente'


def test_serve_document_accepts_the_authorization_header(client, db):
  # La query e' il ripiego per i tag <img>/<a download>, non un sostituto:
  # l'header deve funzionare, altrimenti il documento non e' scaricabile via
  # fetch e il token e' costretto a finire nell'URL.
  response = client.get('/rae/dtr-documents/1.pdf', headers=auth_header(create_user(UserRole.ADMIN)))

  assert response.status_code == 404


@pytest.mark.parametrize('role', [UserRole.CUSTOMER, UserRole.DELIVERY])
def test_serve_document_rejects_other_roles(client, db, role):
  response = client.get(f'/rae/dtr-documents/1.pdf?token={query_token(role)}')

  assert response.get_json()['message'] == 'Ruolo non autorizzato'


@pytest.mark.parametrize('role', [UserRole.ADMIN, UserRole.OPERATOR])
def test_serve_document_rejects_unknown_folder(client, db, role):
  response = client.get(f'/rae/cartella-non-valida/1.pdf?token={query_token(role)}')

  body = response.get_json()
  assert body['status'] == 'ko'
  assert body['message'] == 'Invalid folder'


@pytest.mark.parametrize('role', [UserRole.ADMIN, UserRole.OPERATOR])
def test_serve_document_returns_404_for_missing_file(client, db, role):
  response = client.get(f'/rae/dtr-documents/non-esiste.pdf?token={query_token(role)}')

  assert response.status_code == 404

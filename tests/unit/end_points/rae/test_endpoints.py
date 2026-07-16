"""Test delle route generiche di src/end_points/rae/__init__.py."""


def test_serve_document_rejects_unknown_folder(client):
  response = client.get('/rae/cartella-non-valida/1.pdf')

  body = response.get_json()
  assert body['status'] == 'ko'
  assert body['message'] == 'Invalid folder'


def test_serve_document_returns_404_for_missing_file(client):
  response = client.get('/rae/dtr-documents/non-esiste.pdf')

  assert response.status_code == 404

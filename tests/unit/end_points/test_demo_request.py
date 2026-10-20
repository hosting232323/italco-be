import pytest

from database_api import Session

from src.database.schema import Mail
from src import rate_limit
from src.end_points import demo_request


VALID = {
  'nome': 'Mario Rossi',
  'azienda': 'Rossi Logistica SRL',
  'email': 'mario@rossi.it',
  'cellulare': '+39 333 1234567',
}


@pytest.fixture(autouse=True)
def mailer(monkeypatch):
  rate_limit._attempts.clear()
  monkeypatch.setattr(demo_request, 'DEMO_REQUEST_EMAILS', ['uno@hubstra.it', 'due@hubstra.it'])
  sent = []

  def fake_send(email, body, subject, **kwargs):
    sent.append((email, body, subject))
    return True

  monkeypatch.setattr(demo_request, 'send_email', fake_send)
  return sent


def post(client, payload, **kwargs):
  return client.post('/demo-request', json=payload, **kwargs)


def test_sends_to_configured_recipients_and_stores_mails(client, mailer):
  response = post(
    client, {**VALID, 'citta': 'Bari', 'messaggio': 'Vorrei una demo'}, headers={'Origin': 'https://hubstra.it'}
  )

  assert response.status_code == 200
  assert response.get_json()['status'] == 'ok'
  assert [m[0] for m in mailer] == ['uno@hubstra.it', 'due@hubstra.it']
  _, body, subject = mailer[0]
  assert subject == 'Richiesta demo HUBSTRA — Rossi Logistica SRL'
  assert 'Nome: Mario Rossi' in body
  assert 'Email aziendale: mario@rossi.it' in body
  assert 'Città: Bari' in body
  assert 'Partita IVA: Non indicato' in body
  assert body.endswith('Vorrei una demo')

  with Session() as session:
    saved = session.query(Mail).order_by(Mail.id).all()
  assert [m.recipient for m in saved] == ['uno@hubstra.it', 'due@hubstra.it']
  assert saved[0].origin == 'https://hubstra.it'
  assert saved[0].content == body


def test_recipient_is_never_taken_from_the_client(client, mailer):
  post(client, {**VALID, 'recipient': 'vittima@example.com', 'to': 'vittima@example.com'})

  assert 'vittima@example.com' not in [m[0] for m in mailer]


@pytest.mark.parametrize('missing', ['nome', 'azienda', 'email', 'cellulare'])
def test_required_fields(client, mailer, missing):
  response = post(client, {**VALID, missing: '  '})

  assert response.status_code == 400
  assert response.get_json()['status'] == 'ko'
  assert mailer == []


@pytest.mark.parametrize(
  'override',
  [
    {'email': 'non-una-email'},
    {'email': 'a@b'},
    {'cellulare': '12'},
    {'nome': 'x' * 101},
    {'messaggio': 'x' * 2001},
    {'azienda': 123},
  ],
)
def test_invalid_values_are_rejected(client, mailer, override):
  response = post(client, {**VALID, **override})

  assert response.status_code == 400
  assert mailer == []


def test_invalid_body_is_rejected(client, mailer):
  assert client.post('/demo-request', data='non json', content_type='text/plain').status_code == 400
  assert post(client, ['lista']).status_code == 400
  assert mailer == []


def test_control_characters_cannot_split_the_subject(client, mailer):
  post(client, {**VALID, 'azienda': 'Rossi\r\nBcc: spam@example.com'})

  subject = mailer[0][2]
  assert '\r' not in subject and '\n' not in subject


def test_honeypot_is_silently_discarded(client, mailer):
  response = post(client, {**VALID, 'sito_web': 'http://spam'})

  assert response.get_json()['status'] == 'ok'
  assert mailer == []
  with Session() as session:
    assert session.query(Mail).count() == 0


def test_rate_limit_per_ip(client, mailer):
  for _ in range(demo_request.RATE_LIMIT_MAX):
    assert post(client, VALID, headers={'X-Forwarded-For': '1.2.3.4'}).status_code == 200

  assert post(client, VALID, headers={'X-Forwarded-For': '1.2.3.4'}).status_code == 429
  assert post(client, VALID, headers={'X-Forwarded-For': '5.6.7.8'}).status_code == 200


def test_reports_failure_when_no_email_is_delivered(client, monkeypatch):
  monkeypatch.setattr(demo_request, 'send_email', lambda *args, **kwargs: False)

  response = post(client, VALID)

  assert response.status_code == 502
  assert response.get_json()['status'] == 'ko'
  # Il contatto resta comunque in archivio.
  with Session() as session:
    assert session.query(Mail).count() == 2


def test_ok_when_at_least_one_recipient_is_reached(client, monkeypatch):
  monkeypatch.setattr(demo_request, 'send_email', lambda email, *args, **kwargs: email == 'due@hubstra.it')

  assert post(client, VALID).get_json()['status'] == 'ok'

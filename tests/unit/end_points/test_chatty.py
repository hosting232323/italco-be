import json
from datetime import date
from types import SimpleNamespace

import src.end_points.chatty as chatty
from src.database.enum import UserRole
from src.database.schema import Chatty

from database_api import Session
from database_api.operations import create

from tests.unit.factories import auth_header, create_order, create_product, create_user, customer_with_service


class FakeThreads:
  def __init__(self, client):
    self._client = client
    self.messages = FakeMessages(client)
    self.runs = FakeRuns(client)

  def create(self):
    self._client.created_threads += 1
    return SimpleNamespace(id='thread-nuovo')


class FakeMessages:
  def __init__(self, client):
    self._client = client

  def create(self, thread_id, role, content):
    self._client.user_messages.append((thread_id, role, content))

  def list(self, thread_id):
    text = SimpleNamespace(value=self._client.reply_text)
    message = SimpleNamespace(role='assistant', content=[SimpleNamespace(text=text)])
    return SimpleNamespace(data=[message])


class FakeRuns:
  def __init__(self, client):
    self._client = client

  def create(self, thread_id, assistant_id):
    return SimpleNamespace(id='run-1')

  def retrieve(self, thread_id, run_id):
    return self._client.statuses.pop(0)

  def submit_tool_outputs(self, thread_id, run_id, tool_outputs):
    self._client.tool_outputs.append(tool_outputs)


class FakeOpenAI:
  def __init__(self, statuses=None, reply_text='Risposta assistente'):
    self.created_threads = 0
    self.user_messages = []
    self.tool_outputs = []
    self.reply_text = reply_text
    self.statuses = statuses or [SimpleNamespace(status='completed')]
    self.beta = SimpleNamespace(threads=FakeThreads(self))


def _tool_call_status(arguments):
  tool_call = SimpleNamespace(
    id='call-1',
    function=SimpleNamespace(name='get_order_for_chatty', arguments=arguments),
  )
  return SimpleNamespace(
    status='requires_action',
    required_action=SimpleNamespace(submit_tool_outputs=SimpleNamespace(tool_calls=[tool_call])),
  )


def test_send_message_creates_thread_and_returns_reply(client, monkeypatch):
  fake = FakeOpenAI()
  monkeypatch.setattr(chatty, 'client', fake)
  admin = create_user(UserRole.ADMIN)

  response = client.post('/chatty/chat', json={'message': 'Ciao'}, headers=auth_header(admin))

  body = response.get_json()
  assert body['status'] == 'ok'
  assert body['session_id'] == 'thread-nuovo'
  assert body['response'] == 'Risposta assistente'
  assert fake.created_threads == 1
  assert 'Ciao' in fake.user_messages[0][2]
  with Session() as session:
    assert session.query(Chatty).filter_by(thread_id='thread-nuovo').count() == 1


def test_send_message_reuses_existing_thread(client, monkeypatch):
  fake = FakeOpenAI()
  monkeypatch.setattr(chatty, 'client', fake)
  admin = create_user(UserRole.ADMIN)
  create(Chatty, {'thread_id': 'thread-esistente', 'user_id': admin.id})

  response = client.post(
    '/chatty/chat', json={'message': 'Ancora', 'session_id': 'thread-esistente'}, headers=auth_header(admin)
  )

  assert response.get_json()['session_id'] == 'thread-esistente'
  assert fake.created_threads == 0
  with Session() as session:
    assert session.query(Chatty).count() == 1


def test_send_message_records_the_owner_of_a_new_thread(client, monkeypatch):
  monkeypatch.setattr(chatty, 'client', FakeOpenAI())
  customer = create_user(UserRole.CUSTOMER)

  client.post('/chatty/chat', json={'message': 'Ciao'}, headers=auth_header(customer))

  with Session() as session:
    assert session.query(Chatty.user_id).filter_by(thread_id='thread-nuovo').scalar() == customer.id


def test_send_message_refuses_a_thread_of_another_user(client, monkeypatch):
  fake = FakeOpenAI()
  monkeypatch.setattr(chatty, 'client', fake)
  owner = create_user(UserRole.CUSTOMER)
  intruder = create_user(UserRole.CUSTOMER)
  create(Chatty, {'thread_id': 'thread-altrui', 'user_id': owner.id})

  response = client.post(
    '/chatty/chat', json={'message': 'Leggo io', 'session_id': 'thread-altrui'}, headers=auth_header(intruder)
  )

  assert response.get_json() == {'status': 'ko', 'message': 'Conversazione non trovata'}
  assert fake.user_messages == []


def test_send_message_refuses_an_unknown_thread(client, monkeypatch):
  fake = FakeOpenAI()
  monkeypatch.setattr(chatty, 'client', fake)
  admin = create_user(UserRole.ADMIN)

  response = client.post(
    '/chatty/chat', json={'message': 'Ancora', 'session_id': 'thread-inventato'}, headers=auth_header(admin)
  )

  assert response.get_json()['status'] == 'ko'
  assert fake.user_messages == []


def test_send_message_resolves_tool_call_with_orders(client, monkeypatch):
  today = date.today().strftime('%Y-%m-%d')
  fake = FakeOpenAI(
    statuses=[
      _tool_call_status(json.dumps({'start_date': today})),
      SimpleNamespace(status='completed'),
    ]
  )
  monkeypatch.setattr(chatty, 'client', fake)
  admin = create_user(UserRole.ADMIN)
  _, _, service_user, _ = customer_with_service()
  order = create_order(addressee='Chatty Cliente')
  create_product(order, service_user)

  response = client.post('/chatty/chat', json={'message': 'ordini di oggi'}, headers=auth_header(admin))

  assert response.get_json()['status'] == 'ok'
  assert len(fake.tool_outputs) == 1
  output = fake.tool_outputs[0][0]['output']
  assert 'Chatty Cliente' in output
  assert f'dal {today}' in output


def test_get_thread_messages(client, monkeypatch):
  fake = FakeOpenAI(reply_text='Contenuto thread')
  monkeypatch.setattr(chatty, 'client', fake)
  admin = create_user(UserRole.ADMIN)
  create(Chatty, {'thread_id': 'thread-x', 'user_id': admin.id})

  response = client.get('/chatty/thread/thread-x', headers=auth_header(admin))

  body = response.get_json()
  assert body['status'] == 'ok'
  assert body['messages'] == [{'role': 'assistant', 'text': 'Contenuto thread'}]


def test_get_thread_messages_requires_login(client, monkeypatch):
  monkeypatch.setattr(chatty, 'client', FakeOpenAI(reply_text='Contenuto thread'))
  owner = create_user(UserRole.ADMIN)
  create(Chatty, {'thread_id': 'thread-x', 'user_id': owner.id})

  response = client.get('/chatty/thread/thread-x')

  assert response.status_code == 401
  assert 'Contenuto thread' not in response.get_data(as_text=True)


def test_get_thread_messages_of_another_user_is_not_found(client, monkeypatch):
  monkeypatch.setattr(chatty, 'client', FakeOpenAI(reply_text='Contenuto thread'))
  owner = create_user(UserRole.CUSTOMER)
  other_admin = create_user(UserRole.ADMIN)
  create(Chatty, {'thread_id': 'thread-x', 'user_id': owner.id})

  response = client.get('/chatty/thread/thread-x', headers=auth_header(other_admin))

  assert response.get_json() == {'status': 'ko', 'message': 'Conversazione non trovata'}


def test_threads_without_owner_are_no_longer_readable(client, monkeypatch):
  # I thread salvati prima della colonna user_id non hanno proprietario.
  monkeypatch.setattr(chatty, 'client', FakeOpenAI(reply_text='Contenuto thread'))
  admin = create_user(UserRole.ADMIN)
  create(Chatty, {'thread_id': 'thread-vecchio'})

  response = client.get('/chatty/thread/thread-vecchio', headers=auth_header(admin))

  assert response.get_json()['status'] == 'ko'


def test_get_order_for_chatty_filters_by_customer(db):
  customer, _, service_user, _ = customer_with_service()
  order = create_order()
  create_product(order, service_user)
  other_customer, _, other_service_user, _ = customer_with_service()
  other_order = create_order()
  create_product(other_order, other_service_user)

  today = date.today().strftime('%Y-%m-%d')
  orders = chatty.get_order_for_chatty(customer, start_date=today)

  assert [o['id'] for o in orders] == [order.id]


def test_submit_orders_without_results(monkeypatch):
  fake = FakeOpenAI()
  monkeypatch.setattr(chatty, 'client', fake)

  chatty.submit_orders_to_thread_dynamic('t', 'r', 'c', [], 'dal 2026-07-01')

  assert 'Non sono stati trovati ordini' in fake.tool_outputs[0][0]['output']


def test_submit_orders_truncates_oversized_payload(monkeypatch):
  fake = FakeOpenAI()
  monkeypatch.setattr(chatty, 'client', fake)
  monkeypatch.setattr(chatty, 'MAX_TOOL_OUTPUT_BYTES', 200)
  orders = [{'id': index, 'note': 'x' * 120} for index in range(5)]

  chatty.submit_orders_to_thread_dynamic('t', 'r', 'c', orders, 'dal 2026-07-01')

  output = fake.tool_outputs[0][0]['output']
  assert 'Elenco di ordini troncato' in output
  assert '"id": 4' not in output

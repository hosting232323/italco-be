import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from openai import APITimeoutError, NotFoundError, RateLimitError

import src.end_points.chatty as chatty
from src.database.enum import UserRole
from src.database.schema import Chatty, Company
from database_api import Session, scope
from database_api.operations import create
from tests.unit.factories import auth_header, create_order, create_product, create_user, customer_with_service


def reply(text='Risposta assistente', output=None, status='completed'):
  return SimpleNamespace(id='resp_1', status=status, output=output or [], output_text=text)


def tool_call(arguments, call_id='call_1', name='get_order_for_chatty'):
  return SimpleNamespace(type='function_call', call_id=call_id, name=name, arguments=json.dumps(arguments))


def not_found():
  return NotFoundError(
    'Not found', response=httpx.Response(404, request=httpx.Request('GET', 'https://api.openai.com')), body=None
  )


@pytest.fixture
def fake(monkeypatch):
  fake = SimpleNamespace(conversations=Mock(), responses=Mock())
  fake.conversations.create.side_effect = lambda **kwargs: SimpleNamespace(id='conv_new', **kwargs)
  fake.responses.create.return_value = reply()
  monkeypatch.setattr(chatty, 'client', fake)
  return fake


def existing(fake, user, **metadata):
  fake.conversations.retrieve.return_value = SimpleNamespace(
    id='conv_existing', metadata={**chatty.conversation_metadata(user), **metadata}
  )


def post(client, user, **payload):
  return client.post('/chatty/chat', json={'message': 'Ciao', **payload}, headers=auth_header(user))


def test_send_message_creates_conversation_and_returns_reply(client, fake):
  admin = create_user(UserRole.ADMIN)
  response = post(client, admin, session_id=None)
  assert response.status_code == 200
  assert response.get_json() == {'status': 'ok', 'session_id': 'conv_new', 'response': 'Risposta assistente'}
  request = fake.responses.create.call_args.kwargs
  assert request['conversation'] == 'conv_new'
  assert 'Ciao' in request['input'][0]['content']
  assert str(date.today()) in request['input'][0]['content']
  assert request['tools'] == [chatty.ORDER_TOOL]
  assert fake.conversations.create.call_args.kwargs['metadata'] == chatty.conversation_metadata(admin)
  with Session() as session:
    assert session.query(Chatty).filter_by(thread_id='conv_new').count() == 1


def test_send_message_reuses_conversation(client, fake):
  admin = create_user(UserRole.ADMIN)
  existing(fake, admin)
  response = post(client, admin, session_id='conv_existing')
  assert response.get_json()['session_id'] == 'conv_existing'
  fake.conversations.create.assert_not_called()
  assert fake.responses.create.call_args.kwargs['conversation'] == 'conv_existing'


@pytest.mark.parametrize('session_id', ['thread_old', 'conv_deleted'])
def test_old_or_deleted_session_starts_new_chat(client, fake, session_id):
  admin = create_user(UserRole.ADMIN)
  fake.conversations.retrieve.side_effect = not_found()
  response = post(client, admin, session_id=session_id)
  assert response.get_json()['session_id'] == 'conv_new'
  if session_id.startswith('thread_'):
    fake.conversations.retrieve.assert_not_called()


@pytest.mark.parametrize('metadata', [{'user_id': '999'}, {'company_id': '999'}, {'role': 'Customer'}])
def test_foreign_session_cannot_be_read_or_continued(client, fake, metadata):
  admin = create_user(UserRole.ADMIN)
  existing(fake, admin, **metadata)
  assert post(client, admin, session_id='conv_existing').status_code == 403
  assert client.get('/chatty/thread/conv_existing', headers=auth_header(admin)).status_code == 403
  fake.responses.create.assert_not_called()
  fake.conversations.items.list.assert_not_called()


@pytest.mark.parametrize(
  'payload',
  [
    {},
    {'message': ''},
    {'message': '  '},
    {'message': 123},
    [],
    {'message': 'Ciao', 'session_id': {}},
    {'message': 'Ciao', 'session_id': 'bad'},
  ],
)
def test_invalid_payload_does_not_call_openai(client, fake, payload):
  admin = create_user(UserRole.ADMIN)
  response = client.post('/chatty/chat', json=payload, headers=auth_header(admin))
  assert response.status_code == 400
  fake.responses.create.assert_not_called()
  fake.conversations.create.assert_not_called()


def test_tool_call_resolves_requested_order_id(client, fake):
  admin = create_user(UserRole.ADMIN)
  _, _, service_user, _ = customer_with_service()
  order = create_order(addressee='Chatty Cliente')
  create_product(order, service_user)
  fake.responses.create.side_effect = [
    reply(output=[tool_call({'order_id': order.id, 'start_date': None, 'end_date': None})]),
    reply('Ordine trovato'),
  ]
  response = post(client, admin, message=f'Informazioni consegna id: {order.id}')
  assert response.get_json()['response'] == 'Ordine trovato'
  sent = fake.responses.create.call_args_list[1].kwargs
  assert sent['conversation'] == 'conv_new'
  assert sent['input'][0]['type'] == 'function_call_output'
  assert sent['input'][0]['call_id'] == 'call_1'
  assert 'Chatty Cliente' in sent['input'][0]['output']


def test_multiple_tool_calls_are_submitted_together(client, fake):
  admin = create_user(UserRole.ADMIN)
  fake.responses.create.side_effect = [
    reply(output=[tool_call({'start_date': str(date.today())}, 'call_1'), tool_call({'order_id': 21297}, 'call_2')]),
    reply(),
  ]
  assert post(client, admin).status_code == 200
  outputs = fake.responses.create.call_args.kwargs['input']
  assert [item['call_id'] for item in outputs] == ['call_1', 'call_2']
  assert f'dal {date.today()}' in outputs[0]['output']
  assert 'Non sono stati trovati ordini' in outputs[1]['output']


@pytest.mark.parametrize(
  'arguments',
  [
    {},
    {'start_date': 'bad'},
    {'start_date': '2026-09-04', 'end_date': '2026-09-01'},
    {'order_id': True},
    {'order_id': -1},
    {'customer_id': 1},
    [],
  ],
)
def test_invalid_tool_arguments_return_tool_error(fake, arguments):
  admin = create_user(UserRole.ADMIN)
  output = chatty.execute_tool_call(admin, tool_call(arguments))
  assert 'Parametri di ricerca non validi' in output['output']


def test_malformed_json_and_unknown_tool(fake):
  admin = create_user(UserRole.ADMIN)
  malformed = tool_call({})
  malformed.arguments = '{'
  assert 'Parametri di ricerca non validi' in chatty.execute_tool_call(admin, malformed)['output']
  assert 'Funzione non supportata' in chatty.execute_tool_call(admin, tool_call({}, name='unknown'))['output']


@pytest.mark.parametrize('status', ['failed', 'incomplete', 'cancelled', 'in_progress'])
def test_non_completed_response_returns_error(client, fake, status):
  admin = create_user(UserRole.ADMIN)
  fake.responses.create.return_value = reply(status=status)
  assert post(client, admin).status_code == 502
  assert fake.responses.create.call_count == 1


def test_empty_response_and_tool_loop_are_bounded(client, fake, monkeypatch):
  admin = create_user(UserRole.ADMIN)
  fake.responses.create.return_value = reply('')
  assert post(client, admin).status_code == 502
  fake.responses.create.reset_mock()
  monkeypatch.setattr(chatty, 'MAX_TOOL_ROUNDS', 2)
  fake.responses.create.return_value = reply(output=[tool_call({'order_id': 21297})])
  assert post(client, admin).status_code == 502
  assert fake.responses.create.call_count == 3


@pytest.mark.parametrize('stage', ['create', 'retrieve', 'response'])
def test_openai_failures_return_controlled_error(client, fake, stage):
  admin = create_user(UserRole.ADMIN)
  error = APITimeoutError(request=httpx.Request('POST', 'https://api.openai.com'))
  if stage == 'create':
    fake.conversations.create.side_effect = error
  elif stage == 'retrieve':
    fake.conversations.retrieve.side_effect = error
  else:
    fake.responses.create.side_effect = error
  response = post(client, admin, session_id='conv_existing' if stage == 'retrieve' else None)
  assert response.status_code == 502
  assert response.get_json()['status'] == 'ko'
  assert 'api.openai.com' not in response.get_data(as_text=True)


def test_rate_limit_does_not_expose_upstream_body(client, fake):
  admin = create_user(UserRole.ADMIN)
  fake.responses.create.side_effect = RateLimitError(
    'sensitive upstream text',
    response=httpx.Response(429, request=httpx.Request('POST', 'https://api.openai.com')),
    body=None,
  )
  response = post(client, admin)
  assert response.status_code == 502
  assert 'sensitive' not in response.get_data(as_text=True)


def test_get_history_filters_tool_items_and_preserves_contract(client, fake):
  admin = create_user(UserRole.ADMIN)
  existing(fake, admin)
  fake.conversations.items.list.return_value = iter(
    [
      SimpleNamespace(type='message', role='assistant', content=[SimpleNamespace(type='output_text', text='Risposta')]),
      tool_call({}),
      SimpleNamespace(type='message', role='user', content=[SimpleNamespace(type='input_text', text='Domanda')]),
    ]
  )
  response = client.get('/chatty/thread/conv_existing', headers=auth_header(admin))
  assert response.get_json() == {
    'status': 'ok',
    'thread_id': 'conv_existing',
    'messages': [{'role': 'assistant', 'text': 'Risposta'}, {'role': 'user', 'text': 'Domanda'}],
  }
  fake.conversations.items.list.assert_called_once_with('conv_existing', order='desc')


@pytest.mark.parametrize('thread_id, expected', [('thread_old', 410), ('bad', 400), ('conv_missing', 404)])
def test_unavailable_history(client, fake, thread_id, expected):
  admin = create_user(UserRole.ADMIN)
  fake.conversations.retrieve.side_effect = not_found()
  response = client.get(f'/chatty/thread/{thread_id}', headers=auth_header(admin))
  assert response.status_code == expected


def test_history_requires_authentication(client, fake):
  response = client.get('/chatty/thread/conv_existing')
  assert response.get_json()['status'] != 'ok'
  fake.conversations.retrieve.assert_not_called()


def test_customer_order_queries_remain_scoped(db):
  customer, _, service_user, _ = customer_with_service()
  order = create_order()
  create_product(order, service_user)
  _, _, other_service_user, _ = customer_with_service()
  other_order = create_order()
  create_product(other_order, other_service_user)
  assert [o['id'] for o in chatty.get_order_for_chatty(customer, start_date=str(date.today()))] == [order.id]
  assert [o['id'] for o in chatty.get_order_for_chatty(customer, order_id=order.id)] == [order.id]
  assert chatty.get_order_for_chatty(customer, order_id=other_order.id) == []


def test_order_queries_remain_company_scoped(db):
  admin = create_user(UserRole.ADMIN)
  other_company = create(Company, {'name': 'Other Company'})
  with scope(company_id=other_company.id):
    _, _, service_user, _ = customer_with_service()
    other_order = create_order()
    create_product(other_order, service_user)
  assert chatty.get_order_for_chatty(admin, order_id=other_order.id) == []


def test_delivery_queries_filter_assignments(db, monkeypatch):
  delivery = create_user(UserRole.DELIVERY)
  query = Mock(return_value=[])
  monkeypatch.setattr(chatty, 'query_orders', query)
  chatty.get_order_for_chatty(delivery, order_id=21297)
  assert {'model': 'DeliveryUser', 'field': 'id', 'value': delivery.id} in query.call_args.args[0]


def test_output_truncation_respects_utf8_byte_limit(monkeypatch):
  monkeypatch.setattr(chatty, 'MAX_TOOL_OUTPUT_BYTES', 200)
  output = chatty.format_orders_output([{'id': index, 'note': 'è' * 55} for index in range(5)], 'Ordini')
  assert 'Elenco di ordini troncato' in output
  assert '"id": 4' not in output
  assert len(output.encode('utf-8')) <= 200


def test_model_and_instructions_are_configurable(client, fake, monkeypatch):
  monkeypatch.setenv('OPENAI_MODEL', 'configured-model')
  monkeypatch.setenv('CHATTY_INSTRUCTIONS', 'Istruzioni personalizzate')
  admin = create_user(UserRole.ADMIN)
  assert post(client, admin).status_code == 200
  assert fake.responses.create.call_args.kwargs['model'] == 'configured-model'
  assert fake.responses.create.call_args.kwargs['instructions'] == 'Istruzioni personalizzate'


def test_real_sdk_serializes_responses_and_reads_paginated_history(client, monkeypatch):
  from openai import OpenAI

  admin = create_user(UserRole.ADMIN)
  requests = []
  metadata = chatty.conversation_metadata(admin)

  def message_item(identifier, role, text):
    content_type = 'output_text' if role == 'assistant' else 'input_text'
    return {
      'id': identifier,
      'type': 'message',
      'role': role,
      'status': 'completed',
      'content': [{'type': content_type, 'text': text, 'annotations': []}],
    }

  def response_body(output):
    return {
      'id': 'resp_sdk',
      'object': 'response',
      'created_at': 0,
      'status': 'completed',
      'model': 'gpt-4.1-mini',
      'output': output,
      'parallel_tool_calls': True,
      'tool_choice': 'auto',
      'tools': [],
      'temperature': 1,
      'top_p': 1,
    }

  def handler(request):
    requests.append(request)
    if request.url.path == '/v1/conversations':
      assert json.loads(request.content)['metadata'] == metadata
      return httpx.Response(
        200, json={'id': 'conv_sdk', 'object': 'conversation', 'created_at': 0, 'metadata': metadata}
      )
    if request.url.path == '/v1/conversations/conv_sdk':
      return httpx.Response(
        200, json={'id': 'conv_sdk', 'object': 'conversation', 'created_at': 0, 'metadata': metadata}
      )
    if request.url.path == '/v1/responses':
      body = json.loads(request.content)
      assert body['conversation'] == 'conv_sdk'
      if body['input'][0].get('role') == 'user':
        return httpx.Response(
          200,
          json=response_body(
            [
              {
                'id': 'fc_sdk',
                'type': 'function_call',
                'call_id': 'call_sdk',
                'name': 'get_order_for_chatty',
                'arguments': '{"order_id":21297,"start_date":null,"end_date":null}',
                'status': 'completed',
              }
            ]
          ),
        )
      assert body['input'][0]['call_id'] == 'call_sdk'
      assert 'Non sono stati trovati ordini' in body['input'][0]['output']
      return httpx.Response(200, json=response_body([message_item('msg_reply', 'assistant', 'Nessun ordine trovato')]))
    assert request.url.path == '/v1/conversations/conv_sdk/items'
    assert request.url.params['order'] == 'desc'
    if request.url.params.get('after'):
      return httpx.Response(
        200,
        json={
          'object': 'list',
          'data': [message_item('msg_question', 'user', 'Consegna 21297')],
          'has_more': False,
          'first_id': 'msg_question',
          'last_id': 'msg_question',
        },
      )
    return httpx.Response(
      200,
      json={
        'object': 'list',
        'data': [message_item('msg_reply', 'assistant', 'Nessun ordine trovato')],
        'has_more': True,
        'first_id': 'msg_reply',
        'last_id': 'msg_reply',
      },
    )

  with OpenAI(api_key='test-only', http_client=httpx.Client(transport=httpx.MockTransport(handler))) as sdk:
    monkeypatch.setattr(chatty, 'client', sdk)
    response = post(client, admin, message='Consegna 21297')
    assert response.status_code == 200
    assert response.get_json()['response'] == 'Nessun ordine trovato'
    history = client.get('/chatty/thread/conv_sdk', headers=auth_header(admin))
    assert history.status_code == 200
    assert history.get_json()['messages'] == [
      {'role': 'assistant', 'text': 'Nessun ordine trovato'},
      {'role': 'user', 'text': 'Consegna 21297'},
    ]
  assert all('/threads' not in str(request.url) and '/assistants' not in str(request.url) for request in requests)

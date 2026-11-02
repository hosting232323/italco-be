from unittest.mock import patch

from sqlalchemy.orm.exc import UnmappedInstanceError

from src import app
from src.database.enum import UserRole
from src.error_handling import client_error_message, handle_client_error

from tests.unit.factories import auth_header, create_user


def test_client_error_message_recognises_input_mistakes():
  assert client_error_message(KeyError('filters')) == 'Campo mancante: filters'
  assert (
    client_error_message(ValueError("invalid literal for int() with base 10: 'abc'")) == 'Identificativo non valido'
  )
  assert client_error_message(UnmappedInstanceError(None)) == 'Elemento non trovato'
  assert client_error_message(TypeError('list indices must be integers or slices, not str')) == 'Dati non validi'
  assert client_error_message(TypeError("'x' is an invalid keyword argument for Model")) == 'Dati non validi'
  assert client_error_message(AttributeError("'list' object has no attribute 'get'")) == 'Dati non validi'


def test_client_error_message_ignores_real_bugs():
  assert client_error_message(RuntimeError('boom')) is None
  assert client_error_message(ValueError('qualcos altro')) is None
  assert client_error_message(TypeError('unsupported operand')) is None
  assert client_error_message(AttributeError("'NoneType' object has no attribute 'id'")) is None


@patch('api.hooks.send_telegram_error')
def test_malformed_input_answers_with_the_reason_and_sends_no_alert(mock_telegram, client):
  admin = create_user(UserRole.ADMIN)

  missing = client.post('/order/filter', json={}, headers=auth_header(admin)).get_json()
  bad_id = client.delete('/transport/abc', headers=auth_header(admin)).get_json()
  not_found = client.delete('/transport/99999999', headers=auth_header(admin)).get_json()

  assert missing == {'status': 'ko', 'message': 'Campo mancante: filters'}
  assert bad_id == {'status': 'ko', 'message': 'Identificativo non valido'}
  assert not_found == {'status': 'ko', 'message': 'Elemento non trovato'}
  mock_telegram.assert_not_called()


@patch('api.hooks.send_telegram_error')
def test_real_bugs_still_reach_the_generic_handler_and_telegram(mock_telegram):
  with app.test_request_context('/'):
    try:
      raise ValueError('un guasto vero')
    except ValueError as error:
      body, status = handle_client_error(error)

  assert (body, status) == ({'status': 'ko', 'message': 'Errore generico'}, 200)
  mock_telegram.assert_called_once()


def test_http_exceptions_pass_through_untouched():
  from werkzeug.exceptions import NotFound

  error = NotFound()
  assert handle_client_error(error) is error

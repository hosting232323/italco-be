"""Errori di input del client: messaggio chiaro, niente allarme Telegram.

L'handler globale di generic-lib trasforma ogni eccezione in `{"status": "ko", "message": "Errore generico"}`
(HTTP 200) e ne manda il traceback a Telegram. Un id non numerico, un campo mancante nel JSON o un oggetto che non
esiste non sono guasti del server: qui si riconoscono per tipo e messaggio, si risponde con il motivo e il traceback
non parte. Tutto il resto passa all'handler della libreria come prima.

Il formato di risposta resta quello del resto dell'app (HTTP 200, `status: ko`): il frontend lo legge cosi'.
"""

from api import hooks
from sqlalchemy.orm.exc import UnmappedInstanceError
from werkzeug.exceptions import HTTPException


def client_error_message(error: Exception) -> str | None:
  """Il motivo da mostrare se `error` e' un input sbagliato del client, altrimenti None."""
  message = str(error)
  if isinstance(error, KeyError):
    return f'Campo mancante: {message.strip(chr(39))}'
  if isinstance(error, ValueError) and message.startswith('invalid literal for int()'):
    return 'Identificativo non valido'
  if isinstance(error, UnmappedInstanceError) and 'NoneType' in message:
    return 'Elemento non trovato'
  if isinstance(error, TypeError) and any(
    marker in message
    for marker in (
      'list indices must be integers',
      'is an invalid keyword argument',
      'is not a mapping',
      'dictionary update sequence',
    )
  ):
    return 'Dati non validi'
  if isinstance(error, AttributeError) and "'list' object has no attribute" in message:
    return 'Dati non validi'
  return None


def handle_client_error(error: Exception):
  if isinstance(error, HTTPException):
    return error
  reason = client_error_message(error)
  if reason is None:
    return hooks.handle_exception(error)
  return {'status': 'ko', 'message': reason}, 200


def register_client_error_handlers(app) -> None:
  for error_class in (KeyError, ValueError, TypeError, AttributeError, UnmappedInstanceError):
    app.register_error_handler(error_class, handle_client_error)

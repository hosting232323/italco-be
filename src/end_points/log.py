from ..database.schema import User, Log
from database_api.operations import create


def save_log(user: User, content: str):
  create(Log, {'user_id': user.id, 'content': content})


def save_log_endpoint(user: User, request_data: str):
  create(Log, {'user_id': user.id, 'content': request_data})

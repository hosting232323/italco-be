import os

from api.settings import IS_DEV
from sqlalchemy import text
from sqlalchemy.orm import Session as session_type


def guess_next_id(session: session_type, model: str) -> int:
  return session.execute(text(f"SELECT nextval('{model}_id_seq')")).scalar()


def guess_extension(mime_type: str) -> str:
  if mime_type == 'image/jpeg':
    return '.jpg'
  if mime_type == 'image/png':
    return '.png'
  if mime_type == 'image/webp':
    return '.webp'

  raise ValueError('Mime type non supportato')


def get_full_path(folder: str, subfolder: str, ignore_dev: bool, filename: str | None = None) -> str:
  if not ignore_dev:
    folder = os.path.join(folder, 'test' if IS_DEV else 'prod')
  if subfolder:
    folder = os.path.join(folder, subfolder)
  return os.path.join(folder, filename) if filename else folder

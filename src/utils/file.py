import os
from sqlalchemy import text
from flask import send_from_directory
from sqlalchemy.orm import Session as session_type

from .. import STATIC_FOLDER, IS_DEV


def serve_file(filename: str, folder: str):
  return send_from_directory(
    os.path.join(STATIC_FOLDER, 'test' if IS_DEV else 'prod', folder),
    filename,
  )


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

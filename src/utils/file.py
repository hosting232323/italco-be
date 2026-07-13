from sqlalchemy import text
from sqlalchemy.orm import Session as session_type


def guess_next_id(session: session_type, model: str) -> int:
  sequence_name = session.execute(
    text("SELECT pg_get_serial_sequence(:table_name, 'id')"),
    {'table_name': model},
  ).scalar_one()
  return session.execute(
    text('SELECT nextval(CAST(:sequence_name AS regclass))'),
    {'sequence_name': sequence_name},
  ).scalar_one()


def guess_extension(mime_type: str) -> str:
  if mime_type == 'image/jpeg':
    return '.jpg'
  if mime_type == 'image/png':
    return '.png'
  if mime_type == 'image/webp':
    return '.webp'

  raise ValueError('Mime type non supportato')

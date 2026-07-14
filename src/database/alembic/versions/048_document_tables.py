"""document tables

Revision ID: 048
Revises: 047
Create Date: 2026-07-09 11:30:55.405013

"""

import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from api.storage import get_full_path


revision: str = '048'
down_revision: Union[str, None] = '047'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FOLDER_RENAMES = [
  ('first-copy-fir-documents', 'fir-first-document'),
  ('fourth-copy-fir-documents', 'fir-fourth-document'),
]


def rename_document_folders(renames: list[tuple[str, str]]) -> None:
  static_folder = os.environ.get('STATIC_FOLDER')
  if not static_folder or not os.path.isdir(static_folder):
    return

  for old_name, new_name in renames:
    old_path = get_full_path(static_folder, old_name)
    new_path = get_full_path(static_folder, new_name)
    if os.path.isdir(old_path) and not os.path.exists(new_path):
      os.rename(old_path, new_path)


def upgrade() -> None:
  op.create_table(
    'fir_first_document',
    sa.Column('link', sa.String(), nullable=False),
    sa.Column('disposal_id', sa.Integer(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(
      ['disposal_id'],
      ['disposal.id'],
    ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('disposal_id'),
  )
  op.create_table(
    'fir_fourth_document',
    sa.Column('link', sa.String(), nullable=False),
    sa.Column('disposal_id', sa.Integer(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(
      ['disposal_id'],
      ['disposal.id'],
    ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('disposal_id'),
  )
  op.create_table(
    'dtr_document',
    sa.Column('link', sa.String(), nullable=False),
    sa.Column('rae_product_id', sa.Integer(), nullable=True),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(
      ['rae_product_id'],
      ['rae_product.id'],
    ),
    sa.PrimaryKeyConstraint('id'),
  )

  op.execute("""
    INSERT INTO dtr_document (link, rae_product_id, created_at, updated_at)
    SELECT link, id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
    FROM rae_product
    WHERE link IS NOT NULL
  """)

  op.execute("""
    INSERT INTO fir_first_document (link, disposal_id, created_at, updated_at)
    SELECT
      replace(first_copy_document_fir, '/first-copy-fir-documents/', '/fir-first-document/'),
      id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
    FROM disposal
    WHERE first_copy_document_fir IS NOT NULL
  """)
  op.execute("""
    INSERT INTO fir_fourth_document (link, disposal_id, created_at, updated_at)
    SELECT
      replace(fourth_copy_document_fir, '/fourth-copy-fir-documents/', '/fir-fourth-document/'),
      id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
    FROM disposal
    WHERE fourth_copy_document_fir IS NOT NULL
  """)
  op.drop_column('disposal', 'first_copy_document_fir')
  op.drop_column('disposal', 'fourth_copy_document_fir')
  op.drop_column('rae_product', 'link')

  rename_document_folders(FOLDER_RENAMES)


def downgrade() -> None:
  op.add_column('rae_product', sa.Column('link', sa.VARCHAR(), autoincrement=False, nullable=True))
  op.add_column('disposal', sa.Column('fourth_copy_document_fir', sa.VARCHAR(), autoincrement=False, nullable=True))
  op.add_column('disposal', sa.Column('first_copy_document_fir', sa.VARCHAR(), autoincrement=False, nullable=True))

  op.execute("""
    UPDATE rae_product
    SET link = (
      SELECT link FROM dtr_document
      WHERE dtr_document.rae_product_id = rae_product.id
      ORDER BY created_at DESC, id DESC
      LIMIT 1
    )
  """)

  op.execute("""
    UPDATE disposal
    SET first_copy_document_fir = (
      SELECT replace(link, '/fir-first-document/', '/first-copy-fir-documents/') FROM fir_first_document
      WHERE fir_first_document.disposal_id = disposal.id
      ORDER BY created_at DESC, id DESC
      LIMIT 1
    ),
    fourth_copy_document_fir = (
      SELECT replace(link, '/fir-fourth-document/', '/fourth-copy-fir-documents/') FROM fir_fourth_document
      WHERE fir_fourth_document.disposal_id = disposal.id
      ORDER BY created_at DESC, id DESC
      LIMIT 1
    )
  """)
  op.drop_table('dtr_document')
  op.drop_table('fir_fourth_document')
  op.drop_table('fir_first_document')

  rename_document_folders([(new_name, old_name) for old_name, new_name in FOLDER_RENAMES])

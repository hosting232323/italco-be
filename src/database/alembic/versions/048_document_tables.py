"""document tables

Revision ID: 048
Revises: 047
Create Date: 2026-07-09 11:30:55.405013

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '048'
down_revision: Union[str, None] = '047'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table(
    'disposal_first_copy_document',
    sa.Column('link', sa.String(), nullable=False),
    sa.Column('disposal_id', sa.Integer(), nullable=True),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(
      ['disposal_id'],
      ['disposal.id'],
    ),
    sa.PrimaryKeyConstraint('id'),
  )
  op.create_table(
    'disposal_fourth_copy_document',
    sa.Column('link', sa.String(), nullable=False),
    sa.Column('disposal_id', sa.Integer(), nullable=True),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(
      ['disposal_id'],
      ['disposal.id'],
    ),
    sa.PrimaryKeyConstraint('id'),
  )
  op.create_table(
    'rae_document',
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
    INSERT INTO rae_document (link, rae_product_id, created_at, updated_at)
    SELECT link, id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
    FROM rae_product
    WHERE link IS NOT NULL
  """)

  op.execute("""
    INSERT INTO disposal_first_copy_document (link, disposal_id, created_at, updated_at)
    SELECT first_copy_document_fir, id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
    FROM disposal
    WHERE first_copy_document_fir IS NOT NULL
  """)
  op.execute("""
    INSERT INTO disposal_fourth_copy_document (link, disposal_id, created_at, updated_at)
    SELECT fourth_copy_document_fir, id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
    FROM disposal
    WHERE fourth_copy_document_fir IS NOT NULL
  """)
  op.drop_column('disposal', 'first_copy_document_fir')
  op.drop_column('disposal', 'fourth_copy_document_fir')
  op.drop_column('rae_product', 'link')


def downgrade() -> None:
  op.add_column('rae_product', sa.Column('link', sa.VARCHAR(), autoincrement=False, nullable=True))
  op.add_column('disposal', sa.Column('fourth_copy_document_fir', sa.VARCHAR(), autoincrement=False, nullable=True))
  op.add_column('disposal', sa.Column('first_copy_document_fir', sa.VARCHAR(), autoincrement=False, nullable=True))

  op.execute("""
    UPDATE rae_product
    SET link = (
      SELECT link FROM rae_document
      WHERE rae_document.rae_product_id = rae_product.id
      ORDER BY created_at DESC, id DESC
      LIMIT 1
    )
  """)

  op.execute("""
    UPDATE disposal
    SET first_copy_document_fir = (
      SELECT link FROM disposal_first_copy_document
      WHERE disposal_first_copy_document.disposal_id = disposal.id
      ORDER BY created_at DESC, id DESC
      LIMIT 1
    ),
    fourth_copy_document_fir = (
      SELECT link FROM disposal_fourth_copy_document
      WHERE disposal_fourth_copy_document.disposal_id = disposal.id
      ORDER BY created_at DESC, id DESC
      LIMIT 1
    )
  """)
  op.drop_table('rae_document')
  op.drop_table('disposal_fourth_copy_document')
  op.drop_table('disposal_first_copy_document')

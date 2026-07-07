"""Document tables

Revision ID: 047
Revises: 046
Create Date: 2026-07-07 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '047'
down_revision: Union[str, None] = '046'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table(
    'rae_document',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('link', sa.String(), nullable=False),
    sa.Column('rae_product_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['rae_product_id'], ['rae_product.id']),
    sa.PrimaryKeyConstraint('id'),
  )
  op.create_table(
    'disposal_document',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('link', sa.String(), nullable=False),
    sa.Column('disposal_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['disposal_id'], ['disposal.id']),
    sa.PrimaryKeyConstraint('id'),
  )

  op.execute("""
    INSERT INTO rae_document (link, rae_product_id, created_at, updated_at)
    SELECT link, id, updated_at, updated_at
    FROM rae_product
    WHERE link IS NOT NULL
  """)
  op.execute("""
    INSERT INTO disposal_document (link, disposal_id, created_at, updated_at)
    SELECT document_fir, id, updated_at, updated_at
    FROM disposal
    WHERE document_fir IS NOT NULL
  """)

  op.execute("""
    SELECT setval('rae_document_id_seq', GREATEST(
      (SELECT COALESCE(MAX(id), 1) FROM rae_document),
      (SELECT last_value FROM rae_product_id_seq)
    ))
  """)
  op.execute("""
    SELECT setval('disposal_document_id_seq', GREATEST(
      (SELECT COALESCE(MAX(id), 1) FROM disposal_document),
      (SELECT last_value FROM disposal_id_seq)
    ))
  """)

  op.drop_column('rae_product', 'link')
  op.drop_column('disposal', 'document_fir')


def downgrade() -> None:
  op.add_column('rae_product', sa.Column('link', sa.String(), nullable=True))
  op.add_column('disposal', sa.Column('document_fir', sa.String(), nullable=True))

  op.execute("""
    UPDATE rae_product rp
    SET link = d.link
    FROM (
      SELECT DISTINCT ON (rae_product_id) rae_product_id, link
      FROM rae_document
      WHERE rae_product_id IS NOT NULL
      ORDER BY rae_product_id, id DESC
    ) d
    WHERE rp.id = d.rae_product_id
  """)
  op.execute("""
    UPDATE disposal ds
    SET document_fir = d.link
    FROM (
      SELECT DISTINCT ON (disposal_id) disposal_id, link
      FROM disposal_document
      WHERE disposal_id IS NOT NULL
      ORDER BY disposal_id, id DESC
    ) d
    WHERE ds.id = d.disposal_id
  """)

  op.drop_table('disposal_document')
  op.drop_table('rae_document')

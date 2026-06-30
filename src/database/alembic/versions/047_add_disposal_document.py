"""add disposal document

Revision ID: 047
Revises: 046
Create Date: 2026-06-30 13:09:44.914160

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '047'
down_revision: Union[str, None] = '046'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('disposal', sa.Column('first_copy_document_fir', sa.String(), nullable=True))
  op.add_column('disposal', sa.Column('fourth_copy_document_fir', sa.String(), nullable=True))

  op.execute("""
    UPDATE disposal
    SET first_copy_document_fir = document_fir
    WHERE document_fir IS NOT NULL
  """)

  op.drop_column('disposal', 'document_fir')


def downgrade() -> None:
  op.add_column('disposal', sa.Column('document_fir', sa.VARCHAR(), autoincrement=False, nullable=True))
  op.execute("""
    UPDATE disposal
    SET document_fir = first_copy_document_fir
    WHERE first_copy_document_fir IS NOT NULL
  """)
  op.drop_column('disposal', 'fourth_copy_document_fir')
  op.drop_column('disposal', 'first_copy_document_fir')

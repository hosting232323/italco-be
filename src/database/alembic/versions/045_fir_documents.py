"""Fir documents

Revision ID: 045
Revises: 044
Create Date: 2026-06-19 14:24:24.558422

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '045'
down_revision: Union[str, None] = '044'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('disposal', sa.Column('document_fir', sa.String(), nullable=True))
  op.alter_column('disposal', 'date', existing_type=postgresql.TIMESTAMP(), type_=sa.Date(), existing_nullable=True)
  op.alter_column(
    'disposal', 'updated_at', existing_type=sa.DATE(), type_=sa.DateTime(timezone=True), existing_nullable=True
  )
  op.drop_column('disposal', 'document_ldr')


def downgrade() -> None:
  op.add_column('disposal', sa.Column('document_ldr', sa.VARCHAR(), autoincrement=False, nullable=True))
  op.alter_column(
    'disposal', 'updated_at', existing_type=sa.DateTime(timezone=True), type_=sa.DATE(), existing_nullable=True
  )
  op.alter_column('disposal', 'date', existing_type=sa.Date(), type_=postgresql.TIMESTAMP(), existing_nullable=True)
  op.drop_column('disposal', 'document_fir')

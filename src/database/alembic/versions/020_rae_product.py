"""Rae Product

Revision ID: 020
Revises: 019
Create Date: 2026-01-24 06:16:40.826645

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '020'
down_revision: Union[str, None] = '019'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table(
    'rae_product',
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('code', sa.Integer(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
  )
  op.add_column('product', sa.Column('rae_product_id', sa.Integer(), nullable=True))
  op.create_foreign_key(None, 'product', 'rae_product', ['rae_product_id'], ['id'])


def downgrade() -> None:
  op.drop_constraint(None, 'product', type_='foreignkey')
  op.drop_column('product', 'rae_product_id')
  op.drop_table('rae_product')

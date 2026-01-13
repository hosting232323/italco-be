"""Motivation order id

Revision ID: 019
Revises: 018
Create Date: 2026-01-13 05:09:51.410912
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '019'
down_revision: Union[str, None] = '018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.drop_constraint(op.f('motivation_id_order_fkey'), 'motivation', type_='foreignkey')
  op.alter_column('motivation', 'id_order', new_column_name='order_id', existing_type=sa.Integer(), nullable=False)
  op.create_foreign_key(None, 'motivation', 'order', ['order_id'], ['id'])


def downgrade() -> None:
  op.drop_constraint(None, 'motivation', type_='foreignkey')
  op.alter_column('motivation', 'order_id', new_column_name='id_order', existing_type=sa.Integer(), nullable=False)
  op.create_foreign_key(op.f('motivation_id_order_fkey'), 'motivation', 'order', ['id_order'], ['id'])

"""Optimistic lock

Revision ID: 042
Revises: 041
Create Date: 2026-06-11 19:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '042'
down_revision: Union[str, None] = '041'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('order', sa.Column('version', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
  op.drop_column('order', 'version')

"""Assignament date

Revision ID: 032
Revises: 031
Create Date: 2026-03-17 20:49:26.810658

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '032'
down_revision: Union[str, None] = '031'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.drop_column('order', 'assignament_date')


def downgrade() -> None:
  op.add_column('order', sa.Column('assignament_date', sa.DATE(), autoincrement=False, nullable=True))

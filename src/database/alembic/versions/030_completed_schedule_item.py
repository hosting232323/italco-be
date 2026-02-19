"""completed schedule item

Revision ID: 030
Revises: 029
Create Date: 2026-02-19 17:13:00.339947

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '030'
down_revision: Union[str, None] = '029'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('schedule_item', sa.Column('completed', sa.Boolean(), nullable=True))


def downgrade() -> None:
  op.drop_column('schedule_item', 'completed')

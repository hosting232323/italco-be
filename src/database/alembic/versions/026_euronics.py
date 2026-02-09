"""Euronics

Revision ID: 026
Revises: 025
Create Date: 2026-02-09 13:24:44.380447

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '026'
down_revision: Union[str, None] = '025'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.alter_column('product', 'service_user_id', existing_type=sa.INTEGER(), nullable=False)


def downgrade() -> None:
  op.alter_column('product', 'service_user_id', existing_type=sa.INTEGER(), nullable=True)

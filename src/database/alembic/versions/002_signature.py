"""Signature

Revision ID: 002
Revises: 001
Create Date: 2025-09-17 15:36:01.454473

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('order', sa.Column('signature', sa.LargeBinary(), nullable=True))


def downgrade() -> None:
  op.drop_column('order', 'signature')

"""Transport and delivery cap

Revision ID: 018
Revises: 017
Create Date: 2025-12-31 18:45:22.180572

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '018'
down_revision: Union[str, None] = '017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('delivery_user_info', sa.Column('cap', sa.String(), nullable=True))
  op.drop_column('delivery_user_info', 'location')
  op.add_column('transport', sa.Column('cap', sa.String(), nullable=True))
  op.drop_column('transport', 'location')


def downgrade() -> None:
  op.add_column('transport', sa.Column('location', sa.VARCHAR(), autoincrement=False, nullable=True))
  op.drop_column('transport', 'cap')
  op.add_column('delivery_user_info', sa.Column('location', sa.VARCHAR(), autoincrement=False, nullable=True))
  op.drop_column('delivery_user_info', 'cap')

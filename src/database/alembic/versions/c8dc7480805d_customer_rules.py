"""Customer Rules

Revision ID: c8dc7480805d
Revises: ec56631a6122
Create Date: 2025-06-23 11:50:51.555196

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c8dc7480805d'
down_revision: Union[str, None] = 'ec56631a6122'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table('customer_rule',
    sa.Column('day_of_week', sa.String(), nullable=False),
    sa.Column('max_orders', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['italco_user.id'], ),
    sa.PrimaryKeyConstraint('id')
  )


def downgrade() -> None:
  op.drop_table('customer_rule')

"""Delivery User Info

Revision ID: 017
Revises: 016
Create Date: 2025-12-14 21:08:15.553859

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '017'
down_revision: Union[str, None] = '016'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table(
    'delivery_user_info',
    sa.Column('location', sa.String(), nullable=True),
    sa.Column('lat', sa.Numeric(precision=11, scale=8), nullable=True),
    sa.Column('lon', sa.Numeric(precision=11, scale=8), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(
      ['user_id'],
      ['user.id'],
    ),
    sa.PrimaryKeyConstraint('id'),
  )
  op.add_column('transport', sa.Column('location', sa.String(), nullable=True))
  op.drop_column('user', 'lat')
  op.drop_column('user', 'lon')


def downgrade() -> None:
  op.add_column('user', sa.Column('lon', sa.NUMERIC(precision=11, scale=8), autoincrement=False, nullable=True))
  op.add_column('user', sa.Column('lat', sa.NUMERIC(precision=11, scale=8), autoincrement=False, nullable=True))
  op.drop_column('transport', 'location')
  op.drop_table('delivery_user_info')

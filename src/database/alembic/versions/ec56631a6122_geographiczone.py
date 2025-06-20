"""GeographicZone

Revision ID: ec56631a6122
Revises: 6855ce8e924d
Create Date: 2025-06-17 21:04:21.961517

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'ec56631a6122'
down_revision: Union[str, None] = '6855ce8e924d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table('geographic_zone',
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
  )
  op.create_table('geographic_code',
    sa.Column('zone_id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(), nullable=False),
    sa.Column('type', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['zone_id'], ['geographic_zone.id'], ),
    sa.PrimaryKeyConstraint('id')
  )
  op.create_table('constraints',
    sa.Column('zone_id', sa.Integer(), nullable=False),
    sa.Column('day_of_week', sa.String(), nullable=False),
    sa.Column('max_orders', sa.Integer(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['zone_id'], ['geographic_zone.id'], ),
    sa.PrimaryKeyConstraint('id')
  )


def downgrade() -> None:
  op.drop_table('constraints')
  op.drop_table('geographic_code')
  op.drop_table('geographic_zone')

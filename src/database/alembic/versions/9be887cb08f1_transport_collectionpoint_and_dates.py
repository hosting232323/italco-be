"""Transport CollectionPoint and dates

Revision ID: 9be887cb08f1
Revises: 65ae084999cc
Create Date: 2025-04-28 19:03:37.555000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9be887cb08f1'
down_revision: Union[str, None] = '65ae084999cc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table('transport',
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('plate', sa.String(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
  )
  op.create_table('transport_delivery_group',
    sa.Column('transport_id', sa.Integer(), nullable=False),
    sa.Column('delivery_group_id', sa.Integer(), nullable=True),
    sa.Column('start', sa.Date(), nullable=False),
    sa.Column('end', sa.Date(), nullable=True),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['delivery_group_id'], ['delivery_group.id'], ),
    sa.ForeignKeyConstraint(['transport_id'], ['transport.id'], ),
    sa.PrimaryKeyConstraint('id')
  )
  op.create_table('collection_point',
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('address', sa.String(), nullable=False),
    sa.Column('city', sa.String(), nullable=False),
    sa.Column('cap', sa.String(), nullable=False),
    sa.Column('province', sa.String(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['italco_user.id'], ),
    sa.PrimaryKeyConstraint('id')
  )
  op.add_column('order', sa.Column('collection_point_id', sa.Integer(), nullable=False))
  op.add_column('order', sa.Column('dpc', sa.Date(), nullable=False))
  op.add_column('order', sa.Column('drc', sa.Date(), nullable=False))
  op.create_foreign_key(None, 'order', 'collection_point', ['collection_point_id'], ['id'])


def downgrade() -> None:
  op.drop_constraint(None, 'order', type_='foreignkey')
  op.drop_column('order', 'drc')
  op.drop_column('order', 'dpc')
  op.drop_column('order', 'collection_point_id')
  op.drop_table('collection_point')
  op.drop_table('transport_delivery_group')
  op.drop_table('transport')

"""Addressee and Delivery Group

Revision ID: 65ae084999cc
Revises: 91f1daf4691c
Create Date: 2025-04-24 21:13:59.760712

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '65ae084999cc'
down_revision: Union[str, None] = '91f1daf4691c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table('addressee',
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
  op.create_table('delivery_group',
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
  )
  op.add_column('italco_user', sa.Column('delivery_group_id', sa.Integer(), nullable=True))
  op.create_foreign_key('fk_user_delivery_group', 'italco_user', 'delivery_group', ['delivery_group_id'], ['id'])
  op.add_column('order', sa.Column('addresse_id', sa.Integer(), nullable=False))
  op.add_column('order', sa.Column('delivery_group_id', sa.Integer(), nullable=True))
  op.add_column('order', sa.Column('customer_note', sa.String(), nullable=True))
  op.add_column('order', sa.Column('operator_note', sa.String(), nullable=True))
  op.create_foreign_key('fk_order_delivery_group', 'order', 'delivery_group', ['delivery_group_id'], ['id'])
  op.create_foreign_key('fk_order_addressee', 'order', 'addressee', ['addresse_id'], ['id'])
  op.drop_column('order', 'group')
  op.drop_column('order', 'note')
  op.drop_column('order', 'point_of_sale')


def downgrade() -> None:
  op.add_column('order', sa.Column('point_of_sale', sa.VARCHAR(), autoincrement=False, nullable=False))
  op.add_column('order', sa.Column('note', sa.VARCHAR(), autoincrement=False, nullable=True))
  op.add_column('order', sa.Column('group', sa.VARCHAR(), autoincrement=False, nullable=True))
  op.drop_constraint('fk_order_addressee', 'order', type_='foreignkey')
  op.drop_constraint('fk_order_delivery_group', 'order', type_='foreignkey')
  op.drop_column('order', 'operator_note')
  op.drop_column('order', 'customer_note')
  op.drop_column('order', 'delivery_group_id')
  op.drop_column('order', 'addresse_id')
  op.drop_constraint('fk_user_delivery_group', 'italco_user', type_='foreignkey')
  op.drop_column('italco_user', 'delivery_group_id')
  op.drop_table('delivery_group')
  op.drop_table('addressee')

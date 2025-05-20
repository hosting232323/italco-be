"""Startup Database

Revision ID: 6855ce8e924d
Revises: 
Create Date: 2025-05-19 00:00:56.943455

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '6855ce8e924d'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table('customer_group',
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
  )
  op.create_table('delivery_group',
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
  )
  op.create_table('service',
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('type', sa.Enum('DELIVERY', 'WITHDRAW', 'REPLACEMENT', 'CHECK', name='ordertype'), nullable=False),
    sa.Column('description', sa.String(), nullable=True),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
  )
  op.create_table('transport',
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('plate', sa.String(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
  )
  op.create_table('italco_user',
    sa.Column('role', sa.Enum('ADMIN', 'CUSTOMER', 'OPERATOR', 'DELIVERY', name='userrole'), nullable=False),
    sa.Column('customer_group_id', sa.Integer(), nullable=True),
    sa.Column('delivery_group_id', sa.Integer(), nullable=True),
    sa.Column('password', sa.String(), nullable=True),
    sa.Column('pass_token', sa.String(), nullable=True),
    sa.Column('email', sa.String(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['customer_group_id'], ['customer_group.id'], ),
    sa.ForeignKeyConstraint(['delivery_group_id'], ['delivery_group.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
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
  op.create_table('service_user',
    sa.Column('price', sa.Float(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('service_id', sa.Integer(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['service_id'], ['service.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['italco_user.id'], ),
    sa.PrimaryKeyConstraint('id')
  )
  op.create_table('schedule',
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('transport_id', sa.Integer(), nullable=False),
    sa.Column('delivery_group_id', sa.Integer(), nullable=True),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['delivery_group_id'], ['delivery_group.id'], ),
    sa.ForeignKeyConstraint(['transport_id'], ['transport.id'], ),
    sa.PrimaryKeyConstraint('id')
  )
  op.create_table('order',
    sa.Column('status', sa.Enum('PENDING', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED', 'ANOMALY', 'DELAY', name='orderstatus'), nullable=False),
    sa.Column('type', sa.Enum('DELIVERY', 'WITHDRAW', 'REPLACEMENT', 'CHECK', name='ordertype'), nullable=False),
    sa.Column('addressee', sa.String(), nullable=False),
    sa.Column('address', sa.String(), nullable=False),
    sa.Column('cap', sa.String(), nullable=False),
    sa.Column('dpc', sa.Date(), nullable=False),
    sa.Column('drc', sa.Date(), nullable=False),
    sa.Column('booking_date', sa.Date(), nullable=True),
    sa.Column('assignament_date', sa.Date(), nullable=True),
    sa.Column('customer_note', sa.String(), nullable=True),
    sa.Column('operator_note', sa.String(), nullable=True),
    sa.Column('motivation', sa.String(), nullable=True),
    sa.Column('schedule_id', sa.Integer(), nullable=True),
    sa.Column('collection_point_id', sa.Integer(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['collection_point_id'], ['collection_point.id'], ),
    sa.ForeignKeyConstraint(['schedule_id'], ['schedule.id'], ),
    sa.PrimaryKeyConstraint('id')
  )
  op.create_table('order_service_user',
    sa.Column('order_id', sa.Integer(), nullable=False),
    sa.Column('product', sa.String(), nullable=False),
    sa.Column('service_user_id', sa.Integer(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['order_id'], ['order.id'], ),
    sa.ForeignKeyConstraint(['service_user_id'], ['service_user.id'], ),
    sa.PrimaryKeyConstraint('id')
  )
  op.create_table('photo',
    sa.Column('photo', sa.LargeBinary(), nullable=False),
    sa.Column('mime_type', sa.String(), nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['order_id'], ['order.id'], ),
    sa.PrimaryKeyConstraint('id')
  )


def downgrade() -> None:
  op.drop_table('schedule')
  op.drop_table('photo')
  op.drop_table('order_service_user')
  op.drop_table('order')
  op.drop_table('service_user')
  op.drop_table('collection_point')
  op.drop_table('transport_delivery_group')
  op.drop_table('italco_user')
  op.drop_table('transport')
  op.drop_table('service')
  op.drop_table('delivery_group')
  op.drop_table('customer_group')
  filetype_enum = sa.Enum('ADMIN', 'CUSTOMER', 'OPERATOR', 'DELIVERY', name='userrole')
  filetype_enum.drop(op.get_bind(), checkfirst=True)
  filetype_enum = sa.Enum('PENDING', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED', 'ANOMALY', name='orderstatus')
  filetype_enum.drop(op.get_bind(), checkfirst=True)
  filetype_enum = sa.Enum('DELIVERY', 'WITHDRAW', 'REPLACEMENT', 'CHECK', name='ordertype')
  filetype_enum.drop(op.get_bind(), checkfirst=True)

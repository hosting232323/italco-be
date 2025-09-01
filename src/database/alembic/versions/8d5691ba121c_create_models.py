'''Create models

Revision ID: 8d5691ba121c
Revises: 
Create Date: 2025-08-27 20:15:37.315312

'''
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '8d5691ba121c'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table(
      'customer_group', sa.Column('name', sa.String(), nullable=False),
      sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
      sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
      sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
      sa.PrimaryKeyConstraint('id'))
  op.create_table(
      'delivery_group', sa.Column('name', sa.String(), nullable=False),
      sa.Column('lat', sa.Numeric(precision=11, scale=8), nullable=True),
      sa.Column('lon', sa.Numeric(precision=11, scale=8), nullable=True),
      sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
      sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
      sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
      sa.PrimaryKeyConstraint('id'))
  op.create_table(
      'geographic_zone', sa.Column('name', sa.String(), nullable=False),
      sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
      sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
      sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
      sa.PrimaryKeyConstraint('id'))
  op.create_table(
      'service', sa.Column('name', sa.String(), nullable=False),
      sa.Column('type',
                sa.Enum('DELIVERY',
                        'WITHDRAW',
                        'REPLACEMENT',
                        'CHECK',
                        name='ordertype'),
                nullable=False),
      sa.Column('description', sa.String(), nullable=True),
      sa.Column('max_services', sa.Integer(), nullable=True),
      sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
      sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
      sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
      sa.PrimaryKeyConstraint('id'))
  op.create_table(
      'transport', sa.Column('name', sa.String(), nullable=False),
      sa.Column('plate', sa.String(), nullable=False),
      sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
      sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
      sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
      sa.PrimaryKeyConstraint('id'))
  op.create_table(
      'constraints', sa.Column('zone_id', sa.Integer(), nullable=False),
      sa.Column('day_of_week', sa.Integer(), nullable=False),
      sa.Column('max_orders', sa.Integer(), nullable=False),
      sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
      sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
      sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
      sa.ForeignKeyConstraint(
          ['zone_id'],
          ['geographic_zone.id'],
      ), sa.PrimaryKeyConstraint('id'))
  op.create_table(
      'geographic_code', sa.Column('zone_id', sa.Integer(), nullable=False),
      sa.Column('code', sa.String(), nullable=False),
      sa.Column('type', sa.Boolean(), nullable=False),
      sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
      sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
      sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
      sa.ForeignKeyConstraint(
          ['zone_id'],
          ['geographic_zone.id'],
      ), sa.PrimaryKeyConstraint('id'))
  op.create_table(
      'italco_user',
      sa.Column('role',
                sa.Enum('ADMIN',
                        'CUSTOMER',
                        'OPERATOR',
                        'DELIVERY',
                        name='userrole'),
                nullable=False),
      sa.Column('customer_group_id', sa.Integer(), nullable=True),
      sa.Column('delivery_group_id', sa.Integer(), nullable=True),
      sa.Column('password', sa.String(), nullable=True),
      sa.Column('pass_token', sa.String(), nullable=True),
      sa.Column('email', sa.String(), nullable=False),
      sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
      sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
      sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
      sa.ForeignKeyConstraint(
          ['customer_group_id'],
          ['customer_group.id'],
      ), sa.ForeignKeyConstraint(
          ['delivery_group_id'],
          ['delivery_group.id'],
      ), sa.PrimaryKeyConstraint('id'), sa.UniqueConstraint('email'))
  op.create_table(
      'schedule', sa.Column('date', sa.Date(), nullable=False),
      sa.Column('transport_id', sa.Integer(), nullable=False),
      sa.Column('delivery_group_id', sa.Integer(), nullable=True),
      sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
      sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
      sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
      sa.ForeignKeyConstraint(
          ['delivery_group_id'],
          ['delivery_group.id'],
      ), sa.ForeignKeyConstraint(
          ['transport_id'],
          ['transport.id'],
      ), sa.PrimaryKeyConstraint('id'))
  op.create_table(
      'collection_point', sa.Column('name', sa.String(), nullable=False),
      sa.Column('address', sa.String(), nullable=False),
      sa.Column('cap', sa.String(), nullable=False),
      sa.Column('user_id', sa.Integer(), nullable=False),
      sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
      sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
      sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
      sa.ForeignKeyConstraint(
          ['user_id'],
          ['italco_user.id'],
      ), sa.PrimaryKeyConstraint('id'))
  op.create_table(
      'customer_rule', sa.Column('day_of_week', sa.Integer(), nullable=False),
      sa.Column('max_orders', sa.Integer(), nullable=False),
      sa.Column('user_id', sa.Integer(), nullable=False),
      sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
      sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
      sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
      sa.ForeignKeyConstraint(
          ['user_id'],
          ['italco_user.id'],
      ), sa.PrimaryKeyConstraint('id'))
  op.create_table(
      'service_user', sa.Column('price', sa.Float(), nullable=False),
      sa.Column('user_id', sa.Integer(), nullable=False),
      sa.Column('service_id', sa.Integer(), nullable=False),
      sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
      sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
      sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
      sa.ForeignKeyConstraint(
          ['service_id'],
          ['service.id'],
      ), sa.ForeignKeyConstraint(
          ['user_id'],
          ['italco_user.id'],
      ), sa.PrimaryKeyConstraint('id'))
  op.create_table(
      'order',
      sa.Column('status',
                sa.Enum('PENDING',
                        'IN_PROGRESS',
                        'ON_BOARD',
                        'COMPLETED',
                        'CANCELLED',
                        'AT_WAREHOUSE',
                        name='orderstatus'),
                nullable=False),
      sa.Column('type',
                sa.Enum('DELIVERY',
                        'WITHDRAW',
                        'REPLACEMENT',
                        'CHECK',
                        name='ordertype'),
                nullable=False),
      sa.Column('addressee', sa.String(), nullable=False),
      sa.Column('address', sa.String(), nullable=False),
      sa.Column('addressee_contact', sa.String(), nullable=True),
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
      sa.Column('schedule_index', sa.Integer(), nullable=True),
      sa.Column('start_time_slot', sa.Time(), nullable=True),
      sa.Column('end_time_slot', sa.Time(), nullable=True),
      sa.Column('anomaly', sa.Boolean(), nullable=True),
      sa.Column('delay', sa.Boolean(), nullable=True),
      sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
      sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
      sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
      sa.ForeignKeyConstraint(
          ['collection_point_id'],
          ['collection_point.id'],
      ), sa.ForeignKeyConstraint(
          ['schedule_id'],
          ['schedule.id'],
      ), sa.PrimaryKeyConstraint('id'))
  op.create_table(
      'order_service_user', sa.Column('order_id', sa.Integer(),
                                      nullable=False),
      sa.Column('product', sa.String(), nullable=False),
      sa.Column('service_user_id', sa.Integer(), nullable=False),
      sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
      sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
      sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
      sa.ForeignKeyConstraint(
          ['order_id'],
          ['order.id'],
      ), sa.ForeignKeyConstraint(
          ['service_user_id'],
          ['service_user.id'],
      ), sa.PrimaryKeyConstraint('id'))
  op.create_table(
      'photo', sa.Column('photo', sa.LargeBinary(), nullable=False),
      sa.Column('mime_type', sa.String(), nullable=False),
      sa.Column('order_id', sa.Integer(), nullable=False),
      sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
      sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
      sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
      sa.ForeignKeyConstraint(
          ['order_id'],
          ['order.id'],
      ), sa.PrimaryKeyConstraint('id'))


def downgrade() -> None:
  op.drop_table('photo')
  op.drop_table('order_service_user')
  op.drop_table('order')
  op.drop_table('service_user')
  op.drop_table('customer_rule')
  op.drop_table('collection_point')
  op.drop_table('schedule')
  op.drop_table('italco_user')
  op.drop_table('geographic_code')
  op.drop_table('constraints')
  op.drop_table('transport')
  op.drop_table('service')
  op.drop_table('geographic_zone')
  op.drop_table('delivery_group')
  op.drop_table('customer_group')

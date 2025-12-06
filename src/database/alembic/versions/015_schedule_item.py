"""Schedule item

Revision ID: 015
Revises: 014
Create Date: 2025-11-22 12:39:20.101859

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '015'
down_revision: Union[str, None] = '014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table(
    'schedule_item',
    sa.Column('index', sa.Integer(), nullable=True),
    sa.Column('start_time_slot', sa.Time(), nullable=True),
    sa.Column('end_time_slot', sa.Time(), nullable=True),
    sa.Column('schedule_id', sa.Integer(), nullable=False),
    sa.Column('operation_type', sa.Enum('ORDER', 'COLLECTIONPOINT', name='scheduletype'), nullable=True),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(
      ['schedule_id'],
      ['schedule.id'],
    ),
    sa.PrimaryKeyConstraint('id'),
  )
  op.create_table(
    'schedule_item_collection_point',
    sa.Column('collection_point_id', sa.Integer(), nullable=False),
    sa.Column('schedule_item_id', sa.Integer(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(
      ['collection_point_id'],
      ['collection_point.id'],
    ),
    sa.ForeignKeyConstraint(
      ['schedule_item_id'],
      ['schedule_item.id'],
    ),
    sa.PrimaryKeyConstraint('id'),
  )
  op.create_table(
    'schedule_item_order',
    sa.Column('order_id', sa.Integer(), nullable=False),
    sa.Column('schedule_item_id', sa.Integer(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(
      ['schedule_item_id'],
      ['schedule_item.id'],
    ),
    sa.ForeignKeyConstraint(
      ['order_id'],
      ['order.id'],
    ),
    sa.PrimaryKeyConstraint('id'),
  )

  op.execute("""
    INSERT INTO schedule_item (id, index, start_time_slot, end_time_slot, schedule_id, operation_type)
    SELECT id, schedule_index, start_time_slot, end_time_slot, schedule_id, 'ORDER'
    FROM "order"
    WHERE schedule_id IS NOT NULL;
    """)
  op.execute("""
    INSERT INTO schedule_item_order (id, order_id, schedule_item_id)
    SELECT id, id AS order_id, id AS schedule_item_id
    FROM "order"
    WHERE schedule_id IS NOT NULL;
    """)

  op.drop_constraint(op.f('order_schedule_id_fkey'), 'order', type_='foreignkey')
  op.drop_column('order', 'schedule_index')
  op.drop_column('order', 'start_time_slot')
  op.drop_column('order', 'schedule_id')
  op.drop_column('order', 'end_time_slot')


def downgrade() -> None:
  op.add_column('order', sa.Column('end_time_slot', postgresql.TIME(), autoincrement=False, nullable=True))
  op.add_column('order', sa.Column('schedule_id', sa.INTEGER(), autoincrement=False, nullable=True))
  op.add_column('order', sa.Column('start_time_slot', postgresql.TIME(), autoincrement=False, nullable=True))
  op.add_column('order', sa.Column('schedule_index', sa.INTEGER(), autoincrement=False, nullable=True))
  op.create_foreign_key(op.f('order_schedule_id_fkey'), 'order', 'schedule', ['schedule_id'], ['id'])
  op.drop_table('schedule_item_order')
  op.drop_table('schedule_item_collection_point')
  op.drop_table('schedule_item')

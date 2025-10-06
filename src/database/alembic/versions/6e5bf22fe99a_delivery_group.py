"""Delivery group

Revision ID: 6e5bf22fe99a
Revises: 981eba745ab5
Create Date: 2025-10-09 16:04:31.031537

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '6e5bf22fe99a'
down_revision: Union[str, None] = '56f8abead30f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.drop_column('delivery_group', 'lat')
  op.drop_column('delivery_group', 'lon')
  op.drop_column('delivery_group', 'name')
  op.add_column('user', sa.Column('lat', sa.Numeric(precision=11, scale=8), nullable=True))
  op.add_column('user', sa.Column('lon', sa.Numeric(precision=11, scale=8), nullable=True))
  op.add_column('delivery_group', sa.Column('schedule_id', sa.Integer(), nullable=True))
  op.add_column('delivery_group', sa.Column('user_id', sa.Integer(), nullable=True))
  op.create_foreign_key('fk_delivery_group_schedule', 'delivery_group', 'schedule', ['schedule_id'], ['id'])
  op.create_foreign_key('fk_delivery_group_user', 'delivery_group', 'user', ['user_id'], ['id'])
  op.drop_constraint('italco_user_delivery_group_id_fkey', 'user', type_='foreignkey')
  op.drop_constraint('schedule_delivery_group_id_fkey', 'schedule', type_='foreignkey')

  op.execute("""
    UPDATE delivery_group
    SET user_id = "user".id
    FROM "user"
    WHERE "user".delivery_group_id = delivery_group.id
  """)
  op.execute("""
    UPDATE delivery_group
    SET schedule_id = schedule.id
    FROM schedule
    WHERE schedule.delivery_group_id = delivery_group.id
  """)
  op.execute("""
    DELETE FROM delivery_group
    WHERE user_id IS NULL OR schedule_id IS NULL
  """)

  op.drop_column('user', 'delivery_group_id')
  op.drop_column('schedule', 'delivery_group_id')
  op.alter_column('delivery_group', 'schedule_id', nullable=False)
  op.alter_column('delivery_group', 'user_id', nullable=False)


def downgrade() -> None:
  op.add_column('delivery_group', sa.Column('name', sa.VARCHAR(), nullable=True))
  op.add_column('delivery_group', sa.Column('lon', sa.Numeric(precision=11, scale=8), nullable=True))
  op.add_column('delivery_group', sa.Column('lat', sa.Numeric(precision=11, scale=8), nullable=True))
  op.add_column('user', sa.Column('delivery_group_id', sa.Integer(), nullable=True))
  op.add_column('schedule', sa.Column('delivery_group_id', sa.Integer(), nullable=True))
  op.create_foreign_key('user_delivery_group_id_fkey', 'user', 'delivery_group', ['delivery_group_id'], ['id'])
  op.create_foreign_key('schedule_delivery_group_id_fkey', 'schedule', 'delivery_group', ['delivery_group_id'], ['id'])
  op.execute("UPDATE delivery_group SET name = 'Recovered Group' WHERE name IS NULL")
  op.drop_constraint('fk_delivery_group_schedule', 'delivery_group', type_='foreignkey')
  op.drop_constraint('fk_delivery_group_user', 'delivery_group', type_='foreignkey')
  op.drop_column('delivery_group', 'user_id')
  op.drop_column('delivery_group', 'schedule_id')
  op.drop_column('user', 'lon')
  op.drop_column('user', 'lat')
  op.alter_column('delivery_group', 'name', nullable=False)

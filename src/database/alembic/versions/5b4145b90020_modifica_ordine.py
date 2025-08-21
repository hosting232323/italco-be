'''modifica_ordine

Revision ID: 5b4145b90020
Revises: 1a545009f364
Create Date: 2025-08-18 12:42:01.732116

'''
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '5b4145b90020'
down_revision: Union[str, None] = '1a545009f364'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


old_status = postgresql.ENUM(
  'PENDING',
  'IN_PROGRESS',
  'ON_BOARD',
  'COMPLETED',
  'CANCELLED',
  'ANOMALY',
  'DELAY',
  name='orderstatus'
)
new_status = postgresql.ENUM(
  'PENDING',
  'IN_PROGRESS',
  'ON_BOARD',
  'COMPLETED',
  'CANCELLED',
  'AT_WAREHOUSE',
  name='orderstatus'
)


def upgrade() -> None:
  op.drop_column('order', 'status')
  op.execute('DROP TYPE orderstatus')
  new_status.create(op.get_bind(), checkfirst=False)
  op.add_column('order', sa.Column('status', new_status, nullable=False, server_default='PENDING'))

  op.add_column('order', sa.Column('star_time_slot', sa.Time(), nullable=True))
  op.add_column('order', sa.Column('end_time_slot', sa.Time(), nullable=True))
  op.add_column('order', sa.Column('anomaly', sa.Boolean(), nullable=True, default=False))
  op.add_column('order', sa.Column('delay', sa.Boolean(), nullable=True, default=False))
  op.drop_column('order', 'time_slot')


def downgrade() -> None:
  op.drop_column('order', 'status')
  op.execute('DROP TYPE orderstatus')
  old_status.create(op.get_bind(), checkfirst=False)
  op.add_column('order', sa.Column('status', old_status, nullable=False, server_default='PENDING'))

  op.add_column('order', sa.Column('time_slot', postgresql.TIME(), autoincrement=False, nullable=True))
  op.drop_column('order', 'delay')
  op.drop_column('order', 'anomaly')
  op.drop_column('order', 'end_time_slot')
  op.drop_column('order', 'star_time_slot')

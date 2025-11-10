"""Order attributes

Revision ID: 009
Revises: 008
Create Date: 2025-11-10 07:44:53.235168

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '009'
down_revision: Union[str, None] = '008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  sa.Enum(
    'PENDING',
    'IN_PROGRESS',
    'ON_BOARD',
    'COMPLETED',
    'CANCELLED',
    'AT_WAREHOUSE',
    'TO_RESCHEDULE',
    'RESCHEDULED',
    name='orderstatus',
  ).create(op.get_bind(), checkfirst=True)
  op.execute('ALTER TABLE motivation ALTER COLUMN status TYPE orderstatus USING status::text::orderstatus')
  op.add_column('order', sa.Column('mark', sa.Float(), nullable=True))
  op.add_column('order', sa.Column('floor', sa.Integer(), nullable=False, server_default=sa.text('0')))
  op.add_column('order', sa.Column('elevator', sa.Boolean(), nullable=False, server_default=sa.text('false')))
  op.alter_column('order', 'floor', server_default=None)
  op.alter_column('order', 'elevator', server_default=None)
  op.alter_column('order', 'floor', existing_type=sa.INTEGER(), nullable=True)
  op.alter_column('order', 'elevator', existing_type=sa.BOOLEAN(), nullable=True)


def downgrade() -> None:
  op.drop_column('order', 'mark')
  op.drop_column('order', 'elevator')
  op.drop_column('order', 'floor')

"""Status

Revision ID: 030
Revises: 029
Create Date: 2026-02-27 12:26:33.150621

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '030'
down_revision: Union[str, None] = '029'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table(
    'status',
    sa.Column(
      'status',
      postgresql.ENUM(
        'NEW',
        'CONFIRMED',
        'BOOKING',
        'DELIVERED',
        'NOT_DELIVERED',
        'REDELIVERY',
        'REPLACEMENT',
        'CANCELLED',
        'URGENT',
        'VERIFICATION',
        'CANCELLED_TO_BE_REFUNDED',
        'DELETED',
        'AT_WAREHOUSE',
        'TO_RESCHEDULE',
        name='orderstatus',
        create_type=False,
      ),
      nullable=False,
    ),
    sa.Column('order_id', sa.Integer(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(
      ['order_id'],
      ['order.id'],
    ),
    sa.PrimaryKeyConstraint('id'),
  )

  op.execute("""
      INSERT INTO status (status, order_id, created_at, updated_at)
      SELECT status, id, NOW(), NOW()
      FROM "order"
      WHERE status IS NOT NULL
    """)


def downgrade() -> None:
  op.drop_table('status')

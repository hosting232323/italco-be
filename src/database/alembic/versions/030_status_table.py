"""status table

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
  order_status_enum = postgresql.ENUM(
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
  )
  op.create_table(
    'status',
    sa.Column('status', order_status_enum, nullable=False),
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
  op.drop_column('order', 'status')


def downgrade() -> None:
  order_status_enum = postgresql.ENUM(
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
  )

  op.add_column(
    'order',
    sa.Column(
      'status',
      order_status_enum,
      server_default=sa.text("'NEW'::orderstatus"),
      nullable=False,
    ),
  )

  op.execute("""
        UPDATE "order" o
        SET status = s.status
        FROM (
            SELECT DISTINCT ON (order_id)
                order_id,
                status
            FROM status
            ORDER BY order_id, created_at DESC
        ) s
        WHERE o.id = s.order_id
    """)

  op.drop_table('status')

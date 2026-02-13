"""New states

Revision ID: 027
Revises: 026
Create Date: 2026-02-11 17:05:32.533181

"""

from typing import Sequence, Union
from alembic import op


revision: str = '027'
down_revision: Union[str, None] = '026'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


old_values = (
  'PENDING',
  'IN_PROGRESS',
  'ON_BOARD',
  'COMPLETED',
  'CANCELLED',
  'AT_WAREHOUSE',
  'TO_RESCHEDULE',
  'RESCHEDULED',
)

new_values = (
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
)


def upgrade() -> None:
  op.execute('ALTER TYPE orderstatus RENAME TO orderstatus_old')

  op.execute(f'CREATE TYPE orderstatus_new AS ENUM {new_values}')

  op.execute("""
        ALTER TABLE "order"
        ALTER COLUMN status DROP DEFAULT,
        ALTER COLUMN status TYPE orderstatus_new
        USING (
            CASE status::text
                WHEN 'PENDING' THEN 'NEW'
                WHEN 'COMPLETED' THEN 'DELIVERED'
                WHEN 'CANCELLED' THEN 'NOT_DELIVERED'
                WHEN 'ON_BOARD' THEN 'BOOKING'
                WHEN 'IN_PROGRESS' THEN 'CONFIRMED'
                WHEN 'RESCHEDULED' THEN 'REDELIVERY'
                ELSE status::text
            END
        )::orderstatus_new
    """)

  op.execute("""
        ALTER TABLE motivation
        ALTER COLUMN status TYPE orderstatus_new
        USING (
            CASE status::text
                WHEN 'PENDING' THEN 'NEW'
                WHEN 'COMPLETED' THEN 'DELIVERED'
                WHEN 'CANCELLED' THEN 'NOT_DELIVERED'
                WHEN 'ON_BOARD' THEN 'BOOKING'
                WHEN 'IN_PROGRESS' THEN 'CONFIRMED'
                WHEN 'RESCHEDULED' THEN 'REDELIVERY'
                ELSE status::text
            END
        )::orderstatus_new
    """)

  op.execute("""
        ALTER TABLE "order"
        ALTER COLUMN status SET DEFAULT 'NEW'
    """)

  op.execute('DROP TYPE orderstatus_old')

  op.execute('ALTER TYPE orderstatus_new RENAME TO orderstatus')


def downgrade() -> None:
  op.execute(f'CREATE TYPE orderstatus_old AS ENUM {old_values}')
  op.execute("""
        ALTER TABLE "order"
        ALTER COLUMN status DROP DEFAULT,
        ALTER COLUMN status TYPE orderstatus_old
        USING (
            CASE status::text
                WHEN 'NEW' THEN 'PENDING'
                WHEN 'DELIVERED' THEN 'COMPLETED'
                WHEN 'NOT_DELIVERED' THEN 'CANCELLED'
                WHEN 'BOOKING' THEN 'ON_BOARD'
                WHEN 'CONFIRMED' THEN 'IN_PROGRESS'
                WHEN 'REDELIVERY' THEN 'RESCHEDULED'
                ELSE 'PENDING'
            END
        )::orderstatus_old
    """)

  op.execute("""
        ALTER TABLE motivation
        ALTER COLUMN status TYPE orderstatus_old
        USING (
            CASE status::text
                WHEN 'NEW' THEN 'PENDING'
                WHEN 'DELIVERED' THEN 'COMPLETED'
                WHEN 'NOT_DELIVERED' THEN 'CANCELLED'
                WHEN 'BOOKING' THEN 'ON_BOARD'
                WHEN 'CONFIRMED' THEN 'IN_PROGRESS'
                WHEN 'REDELIVERY' THEN 'RESCHEDULED'
                ELSE 'PENDING'
            END
        )::orderstatus_old
    """)

  op.execute("""
        ALTER TABLE "order"
        ALTER COLUMN status SET DEFAULT 'PENDING'
    """)

  op.execute('DROP TYPE orderstatus')

  op.execute('ALTER TYPE orderstatus_old RENAME TO orderstatus')

"""Refactor Status

Revision ID: 039
Revises: 038
Create Date: 2026-04-13 17:10:07.526713

"""

from typing import Sequence, Union

from alembic import op


revision: str = '039'
down_revision: Union[str, None] = '038'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

new_values = (
  'ACQUIRED',
  'BOOKED',
  'SCHEDULED',
  'BOOKING',
  'DELIVERED',
  'NOT_DELIVERED',
  'TO_RESCHEDULE',
  'RESCHEDULED',
)


def upgrade() -> None:
  op.execute("""
    UPDATE history
    SET status = jsonb_set(
      status::jsonb,
      '{value}',
      to_jsonb(
        CASE status->>'value'
          WHEN 'REPLACEMENT' THEN 'RESCHEDULED'

          WHEN 'REDELIVERY' THEN 'NOT_DELIVERED'
          WHEN 'CANCELLED' THEN 'NOT_DELIVERED'
          WHEN 'URGENT' THEN 'NOT_DELIVERED'
          WHEN 'VERIFICATION' THEN 'NOT_DELIVERED'
          WHEN 'CANCELLED_TO_BE_REFUNDED' THEN 'NOT_DELIVERED'
          WHEN 'DELETED' THEN 'NOT_DELIVERED'
          WHEN 'AT_WAREHOUSE' THEN 'NOT_DELIVERED'

          ELSE status->>'value'
        END
      )
    )
    WHERE status->>'type' = 'status'
  """)

  op.execute('ALTER TYPE orderstatus RENAME TO orderstatus_old')
  op.execute(f'CREATE TYPE orderstatus_new AS ENUM {new_values}')

  op.execute("""
      ALTER TABLE "order"
      ALTER COLUMN status DROP DEFAULT,
      ALTER COLUMN status TYPE orderstatus_new
      USING (
        CASE status::text
            WHEN 'REPLACEMENT' THEN 'RESCHEDULED'
            
            WHEN 'REDELIVERY' THEN 'NOT_DELIVERED'
            WHEN 'CANCELLED' THEN 'NOT_DELIVERED'
            WHEN 'URGENT' THEN 'NOT_DELIVERED'
            WHEN 'VERIFICATION' THEN 'NOT_DELIVERED'
            WHEN 'CANCELLED_TO_BE_REFUNDED' THEN 'NOT_DELIVERED'
            WHEN 'DELETED' THEN 'NOT_DELIVERED'
            WHEN 'AT_WAREHOUSE' THEN 'NOT_DELIVERED'

            ELSE status::text
        END
      )::orderstatus_new
  """)

  op.execute("""
    ALTER TABLE "motivation"
    ALTER COLUMN status TYPE orderstatus_new
    USING (
        CASE status::text
            WHEN 'REPLACEMENT' THEN 'RESCHEDULED'
            
            WHEN 'REDELIVERY' THEN 'NOT_DELIVERED'
            WHEN 'CANCELLED' THEN 'NOT_DELIVERED'
            WHEN 'URGENT' THEN 'NOT_DELIVERED'
            WHEN 'VERIFICATION' THEN 'NOT_DELIVERED'
            WHEN 'CANCELLED_TO_BE_REFUNDED' THEN 'NOT_DELIVERED'
            WHEN 'DELETED' THEN 'NOT_DELIVERED'
            WHEN 'AT_WAREHOUSE' THEN 'NOT_DELIVERED'

            ELSE status::text
        END
    )::orderstatus_new
  """)

  op.execute('DROP TYPE orderstatus_old')
  op.execute('ALTER TYPE orderstatus_new RENAME TO orderstatus')


def downgrade() -> None:
  pass

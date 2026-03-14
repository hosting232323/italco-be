"""new status

Revision ID: 031
Revises: 030
Create Date: 2026-03-14 12:23:21.486798
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '031'
down_revision: Union[str, None] = '030'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

old_values = (
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
new_values = (
  'ACQUIRED',
  'BOOKED',
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
  'SCHEDULED',
  'AT_WAREHOUSE',
  'TO_RESCHEDULE',
)


def upgrade() -> None:
  op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'euronicsstatus') THEN
                CREATE TYPE euronicsstatus AS ENUM (
                    'NEW','CONFIRMED','BOOKING','DELIVERED','NOT_DELIVERED',
                    'REDELIVERY','REPLACEMENT','CANCELLED','URGENT','VERIFICATION',
                    'CANCELLED_TO_BE_REFUNDED','DELETED'
                );
            END IF;
        END$$;
    """)

  with op.batch_alter_table('order') as batch_op:
    batch_op.add_column(sa.Column('confirmed', sa.Boolean(), nullable=True))

  op.execute("""
        ALTER TABLE "order"
        ALTER COLUMN external_status TYPE euronicsstatus
        USING CASE external_status::text
            WHEN 'NEW' THEN 'NEW'
            WHEN 'CONFIRMED' THEN 'CONFIRMED'
            WHEN 'BOOKING' THEN 'BOOKING'
            WHEN 'DELIVERED' THEN 'DELIVERED'
            WHEN 'NOT_DELIVERED' THEN 'NOT_DELIVERED'
            WHEN 'REDELIVERY' THEN 'REDELIVERY'
            WHEN 'REPLACEMENT' THEN 'REPLACEMENT'
            WHEN 'CANCELLED' THEN 'CANCELLED'
            WHEN 'URGENT' THEN 'URGENT'
            WHEN 'VERIFICATION' THEN 'VERIFICATION'
            WHEN 'CANCELLED_TO_BE_REFUNDED' THEN 'CANCELLED_TO_BE_REFUNDED'
            WHEN 'DELETED' THEN 'DELETED'
            ELSE NULL
        END::euronicsstatus
    """)

  op.execute(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'orderstatus_new') THEN
                CREATE TYPE orderstatus_new AS ENUM {new_values};
            END IF;
        END$$;
    """)

  dependent_tables = ['order', 'motivation', 'status']
  for table in dependent_tables:
    op.execute(f"""
            ALTER TABLE "{table}" ALTER COLUMN status DROP DEFAULT;
            ALTER TABLE "{table}"
            ALTER COLUMN status TYPE orderstatus_new
            USING CASE status::text
                WHEN 'NEW' THEN 'ACQUIRED'
                WHEN 'CONFIRMED' THEN 'SCHEDULED'
                ELSE status::text
            END::orderstatus_new;
        """)

  op.execute("""
        ALTER TABLE "order"
        ALTER COLUMN status SET DEFAULT 'ACQUIRED';
    """)

  op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'orderstatus') THEN
                DROP TYPE orderstatus CASCADE;
            END IF;
            ALTER TYPE orderstatus_new RENAME TO orderstatus;
        END$$;
    """)


def downgrade() -> None:
  op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'orderstatus_old') THEN
                CREATE TYPE orderstatus_old AS ENUM (
                    'NEW','CONFIRMED','BOOKING','DELIVERED','NOT_DELIVERED',
                    'REDELIVERY','REPLACEMENT','CANCELLED','URGENT','VERIFICATION',
                    'CANCELLED_TO_BE_REFUNDED','DELETED','AT_WAREHOUSE','TO_RESCHEDULE'
                );
            END IF;
        END$$;
    """)

  dependent_tables = ['order', 'motivation', 'status']
  for table in dependent_tables:
    op.execute(f"""
            ALTER TABLE "{table}" ALTER COLUMN status DROP DEFAULT;
            ALTER TABLE "{table}"
            ALTER COLUMN status TYPE orderstatus_old
            USING CASE status::text
                WHEN 'ACQUIRED' THEN 'NEW'
                WHEN 'SCHEDULED' THEN 'CONFIRMED'
                ELSE status::text
            END::orderstatus_old;
        """)

  op.execute("""
        ALTER TABLE "order"
        ALTER COLUMN status SET DEFAULT 'NEW';
    """)

  op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'orderstatus') THEN
                DROP TYPE orderstatus CASCADE;
            END IF;
            ALTER TYPE orderstatus_old RENAME TO orderstatus;
        END$$;
    """)

  with op.batch_alter_table('order') as batch_op:
    batch_op.drop_column('confirmed')

  op.execute("""
        ALTER TABLE "order"
        ALTER COLUMN external_status TYPE text;
    """)
  op.execute('DROP TYPE IF EXISTS euronicsstatus')

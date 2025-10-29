"""Rescheduled

Revision ID: 008
Revises: 007
Create Date: 2025-10-27 12:33:08.295516

"""

from typing import Sequence, Union

from alembic import op


revision: str = '008'
down_revision: Union[str, None] = '007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.execute("ALTER TYPE orderstatus ADD VALUE 'RESCHEDULED';")


def downgrade() -> None:
  op.execute('ALTER TYPE orderstatus RENAME TO orderstatus_old;')
  op.execute("""
    CREATE TYPE orderstatus AS ENUM ('PENDING', 'IN_PROGRESS', 'ON_BOARD', 'COMPLETED', 'CANCELLED', 'AT_WAREHOUSE', 'TO_RESCHEDULE');
  """)
  op.execute("""
    ALTER TABLE "order"
    ALTER COLUMN status DROP DEFAULT,
    ALTER COLUMN status TYPE orderstatus
    USING status::text::orderstatus;
  """)
  op.execute('DROP TYPE orderstatus_old;')

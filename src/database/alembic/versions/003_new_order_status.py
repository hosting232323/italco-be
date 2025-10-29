"""New order status

Revision ID: 003
Revises: 002
Create Date: 2025-10-02 15:10:57.276890

"""

from typing import Sequence, Union

from alembic import op


revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.execute("ALTER TYPE orderstatus ADD VALUE 'TO_RESCHEDULE';")


def downgrade() -> None:
  op.execute('ALTER TYPE orderstatus RENAME TO orderstatus_old;')
  op.execute("""
    CREATE TYPE orderstatus AS ENUM ('PENDING', 'IN_PROGRESS', 'ON_BOARD', 'COMPLETED', 'CANCELLED', 'AT_WAREHOUSE');
  """)
  op.execute("""
    ALTER TABLE "order"
    ALTER COLUMN status DROP DEFAULT,
    ALTER COLUMN status TYPE orderstatus
    USING status::text::orderstatus;
  """)
  op.execute('DROP TYPE orderstatus_old;')

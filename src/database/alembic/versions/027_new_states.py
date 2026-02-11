"""new states

Revision ID: 027
Revises: 026
Create Date: 2026-02-11 17:05:32.533181

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '027'
down_revision: Union[str, None] = '026'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.execute("ALTER TYPE enrichmenttype ADD VALUE IF NOT EXISTS 'SWITCHUP_FILE'")


def downgrade() -> None:
  pass

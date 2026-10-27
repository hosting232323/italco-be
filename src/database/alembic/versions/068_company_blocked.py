"""company blocked

Revision ID: 068
Revises: 067
Create Date: 2026-10-27 12:00:00.000000

Blocco manuale di un'attività da parte del super admin (spento per tutte, nessun backfill).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '068'
down_revision: Union[str, None] = '067'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('company', sa.Column('blocked', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
  op.drop_column('company', 'blocked')

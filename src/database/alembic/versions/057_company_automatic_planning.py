"""company automatic planning flag

Revision ID: 057
Revises: 056
Create Date: 2026-09-07 12:00:00.000000

La pianificazione automatica degli ordini diventa un interruttore per attività.
La colonna nasce false per tutti, come chiesto: nessun backfill, un'attività non
pianifica in automatico finché il super admin non accende il flag dalla gestione
della company.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '057'
down_revision: Union[str, None] = '056'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column(
    'company',
    sa.Column('automatic_planning', sa.Boolean(), nullable=False, server_default='false'),
  )


def downgrade() -> None:
  op.drop_column('company', 'automatic_planning')

"""user automatic planning flag

Revision ID: 065
Revises: 064
Create Date: 2026-09-24 12:00:00.000000

Pianificazione automatica per punto vendita (User con role Customer), gemella
di Company.automatic_planning ma a grana più fine. La colonna nasce true per
tutti, come chiesto: quando un'attività accende il flag globale, ogni suo
punto vendita risulta già abilitato senza bisogno di un backfill separato.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '065'
down_revision: Union[str, None] = '064'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column(
    'user',
    sa.Column('automatic_planning', sa.Boolean(), nullable=False, server_default='true'),
  )


def downgrade() -> None:
  op.drop_column('user', 'automatic_planning')

"""schedule version

Revision ID: 065
Revises: 064
Create Date: 2026-10-19 12:00:00.000000

Il borderò non aveva il controllo di versione degli ordini: un salvataggio da
una pagina aperta prima di un'altra modifica la sovrascriveva in silenzio
(voci tolte, ordini tornati prenotati). Da qui in avanti ogni salvataggio
dell'operatore porta la versione letta e viene rifiutato se nel frattempo e'
cambiata.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '065'
down_revision: Union[str, None] = '064'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('schedule', sa.Column('version', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
  op.drop_column('schedule', 'version')

"""punti di ritiro che ammettono il precarico

G6
G5
Create Date: 2026-10-10 12:00:00.000000

collection_point.preloaded: il punto ammette il precarico. Il precarico di un
ordine vale solo se l'area di copertura accetta precarichi (accepts_preloads) e
almeno un punto di ritiro dell'ordine ha questo flag: quei prodotti si ritirano
il giorno prima, gli altri normalmente.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '076'
down_revision: Union[str, None] = '075'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column(
    'collection_point',
    sa.Column('preloaded', sa.Boolean(), nullable=False, server_default='false'),
  )


def downgrade() -> None:
  op.drop_column('collection_point', 'preloaded')

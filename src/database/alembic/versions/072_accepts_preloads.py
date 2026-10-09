"""aree che accettano precarichi

Revision ID: 072
Revises: 071
Create Date: 2026-10-09 12:00:00.000000

delivery_coverage_entry.accepts_preloads: l'area accetta precarichi, e per i suoi
ordini si offrono solo le fasce dei giorni in cui il veicolo passa gia' dagli
stessi punti di ritiro. order.preloaded: l'ordine e' precaricato (ritiro il
giorno prima della consegna).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '072'
down_revision: Union[str, None] = '071'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column(
    'delivery_coverage_entry',
    sa.Column('accepts_preloads', sa.Boolean(), nullable=False, server_default='false'),
  )
  op.add_column('order', sa.Column('preloaded', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
  op.drop_column('order', 'preloaded')
  op.drop_column('delivery_coverage_entry', 'accepts_preloads')

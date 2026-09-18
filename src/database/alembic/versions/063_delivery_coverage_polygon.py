"""delivery coverage polygon

Revision ID: 063
Revises: 062
Create Date: 2026-09-18 12:00:00.000000

Modalità alternativa al CAP per creare un blocco di copertura: disegnare la
zona sulla mappa. `polygon` è una lista JSON di coppie [lat, lon] (i vertici
nell'ordine di disegno), nullable perché resta obbligatorio solo l'uno o
l'altro tra CAP e polygon (validato in end_points/delivery_coverage.py, non
a livello di DB, come già per _has_overlapping_entry).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '063'
down_revision: Union[str, None] = '062'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('delivery_coverage_entry', sa.Column('polygon', sa.JSON(), nullable=True))


def downgrade() -> None:
  op.drop_column('delivery_coverage_entry', 'polygon')

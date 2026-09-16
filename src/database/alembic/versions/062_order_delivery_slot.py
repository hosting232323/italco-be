"""order delivery slot

Revision ID: 062
Revises: 061
Create Date: 2026-09-11 12:00:00.000000

Fascia oraria assegnata automaticamente all'ordine in base alla copertura
corrieri (DeliveryCoverageEntry) quando il cliente sceglie la data prevista.
Nullable: gli ordini esistenti non ne hanno una, e chi crea/modifica un
ordine come operatore/admin non passa dal check-constraints.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '062'
down_revision: Union[str, None] = '061'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('order', sa.Column('delivery_slot_start', sa.Time(), nullable=True))
  op.add_column('order', sa.Column('delivery_slot_end', sa.Time(), nullable=True))


def downgrade() -> None:
  op.drop_column('order', 'delivery_slot_end')
  op.drop_column('order', 'delivery_slot_start')

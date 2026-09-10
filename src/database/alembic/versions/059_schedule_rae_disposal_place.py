"""schedule rae disposal place

Revision ID: 059
Revises: 058
Create Date: 2026-09-10 09:00:00.000000

Il luogo di smaltimento RAEE non viene più chiesto nel form di smaltimento
quando i luoghi sono più di uno: lo si sceglie una volta sola nel borderò che
raccoglie gli ordini con prodotti RAE, e lo smaltimento lo eredita da lì.

schedule prende quindi una FK opzionale a rae_disposal_place: i borderò senza
ordini RAE non la valorizzano, l'obbligatorietà condizionata la impone
l'endpoint. Nessun backfill: i borderò storici restano a NULL.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '059'
down_revision: Union[str, None] = '058'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('schedule', sa.Column('rae_disposal_place_id', sa.Integer(), nullable=True))
  op.create_foreign_key(
    'fk_schedule_rae_disposal_place_id', 'schedule', 'rae_disposal_place', ['rae_disposal_place_id'], ['id']
  )


def downgrade() -> None:
  op.drop_constraint('fk_schedule_rae_disposal_place_id', 'schedule', type_='foreignkey')
  op.drop_column('schedule', 'rae_disposal_place_id')

"""company rae flag

Revision ID: 051
Revises: 050
Create Date: 2026-08-22 10:12:44.318907

Il modulo RAEE diventa opzionale per attività. La colonna nasce false, come
chiesto: un'attività nuova non vede il RAEE finché il super admin non lo accende.

Il backfill però non è false per tutti. Le company già esistenti al momento
della migration che hanno dati RAEE (raggruppamenti, prodotti o smaltimenti)
lo stanno usando davvero: spegnerle qui vorrebbe dire far sparire pagine e
documenti a chi ci lavora ogni giorno. Per loro il flag parte acceso, e chi
non ha mai toccato il RAEE resta a false.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '051'
down_revision: Union[str, None] = '050'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('company', sa.Column('rae', sa.Boolean(), nullable=False, server_default='false'))

  op.execute(
    sa.text("""
      UPDATE company SET rae = true WHERE id IN (
        SELECT company_id FROM rae_product_group
        UNION SELECT company_id FROM rae_product
        UNION SELECT company_id FROM disposal
      )
    """)
  )


def downgrade() -> None:
  op.drop_column('company', 'rae')

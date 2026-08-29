"""company legal info for PDF rendering

Revision ID: 054
Revises: 053
Create Date: 2026-08-28 10:00:00.000000

Sposta su company i dati legali dell'attività che i template PDF tenevano
scritti a mano (il DDT RAEE in templates/components/rae.html). Le colonne
nascono nullable: l'unico NOT NULL di company resta name, e l'obbligatorietà
la controlla l'endpoint.

La riga storica "Ares Logistics" viene precompilata con gli stessi valori che
erano hardcoded, così i DDT già emessi e quelli nuovi restano identici finché
il super admin non li aggiorna dal frontend.

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '054'
down_revision: Union[str, None] = '053'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LEGAL_COLUMNS = (
  'logo',
  'legal_name',
  'vat_number',
  'tax_code',
  'address',
  'city',
  'rae_registration',
  'rae_grouping_place',
)

HISTORICAL_COMPANY = 'Ares Logistics'
HISTORICAL_VALUES = {
  'legal_name': 'Italco.Mi Logistribuzioni SRL',
  'vat_number': '02735550747',
  'tax_code': '02735550747',
  'address': 'Via Emmanuele Filiberto 24 A',
  'city': 'Mesagne (BR)',
  'rae_registration': 'RD401S00025192 del 26/02/26',
  'rae_grouping_place': 'Via Brindisi, 160, Mesagne (BR)',
}


def upgrade() -> None:
  for column in LEGAL_COLUMNS:
    op.add_column('company', sa.Column(column, sa.String(), nullable=True))

  op.get_bind().execute(
    sa.text(
      'UPDATE company SET ' + ', '.join(f'{column} = :{column}' for column in HISTORICAL_VALUES) + ' WHERE name = :name'
    ),
    {**HISTORICAL_VALUES, 'name': HISTORICAL_COMPANY},
  )


def downgrade() -> None:
  for column in reversed(LEGAL_COLUMNS):
    op.drop_column('company', column)

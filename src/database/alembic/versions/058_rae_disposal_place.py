"""rae disposal place

Revision ID: 058
Revises: 057
Create Date: 2026-09-05 09:00:00.000000

Un'attività può smaltire RAEE da più luoghi di raggruppamento invece di uno
solo: rae_grouping_place lascia company per le righe di una nuova tabella
figlia, rae_disposal_place (una per luogo, scelta poi dallo smaltimento).

rae_registration resta invece su company: l'iscrizione all'Albo Gestori
Ambientali è dell'attività, una sola, e si compila nello stesso form dei
luoghi quando si accende il modulo RAEE.

Backfill in tre passi, come già fatto per company_id in 050:
1. una riga rae_disposal_place per ogni company con modulo RAEE acceso
   (rae = true), col luogo di raggruppamento che aveva (anche se mai
   compilato: resta nullable, com'era su company). Il filtro è sul flag e non
   sul campo perché una company può avere disposal senza aver mai valorizzato
   rae_grouping_place;
2. disposal.rae_disposal_place_id popolato con l'unica riga appena creata per
   la company di quel disposal - deterministico perché ogni company con rae
   acceso ha a questo punto esattamente un luogo, e ogni disposal esistente
   appartiene a una company con rae acceso (backfillato già in 051);
3. NOT NULL sulla colonna, poi rae_grouping_place viene tolto da company.

Nota operativa: come 050, riscrive righe e aggiunge un vincolo NOT NULL in
ACCESS EXCLUSIVE - finestra di manutenzione, non a caldo.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '058'
down_revision: Union[str, None] = '057'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DEFAULT_PLACE_NAME = 'Sede principale'


def upgrade() -> None:
  op.create_table(
    'rae_disposal_place',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(), nullable=True),
    sa.Column('rae_grouping_place', sa.String(), nullable=True),
    sa.Column('company_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['company_id'], ['company.id'], name='fk_rae_disposal_place_company_id'),
    sa.PrimaryKeyConstraint('id'),
  )

  bind = op.get_bind()
  bind.execute(
    sa.text("""
      INSERT INTO rae_disposal_place (name, rae_grouping_place, company_id, created_at, updated_at)
      SELECT :name, rae_grouping_place, id, now(), now()
      FROM company
      WHERE rae = true
    """),
    {'name': DEFAULT_PLACE_NAME},
  )

  op.add_column('disposal', sa.Column('rae_disposal_place_id', sa.Integer(), nullable=True))
  bind.execute(
    sa.text("""
      UPDATE disposal d SET rae_disposal_place_id = p.id
      FROM rae_disposal_place p
      WHERE p.company_id = d.company_id
    """)
  )
  op.alter_column('disposal', 'rae_disposal_place_id', nullable=False)
  op.create_foreign_key(
    'fk_disposal_rae_disposal_place_id', 'disposal', 'rae_disposal_place', ['rae_disposal_place_id'], ['id']
  )

  op.drop_column('company', 'rae_grouping_place')


def downgrade() -> None:
  op.add_column('company', sa.Column('rae_grouping_place', sa.String(), nullable=True))

  bind = op.get_bind()
  bind.execute(
    sa.text("""
      UPDATE company c SET rae_grouping_place = p.rae_grouping_place
      FROM rae_disposal_place p
      WHERE p.company_id = c.id
    """)
  )

  op.drop_constraint('fk_disposal_rae_disposal_place_id', 'disposal', type_='foreignkey')
  op.drop_column('disposal', 'rae_disposal_place_id')
  op.drop_table('rae_disposal_place')

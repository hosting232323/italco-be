"""add company

Revision ID: 050
Revises: 049
Create Date: 2026-04-07 17:33:57.697326

Introduce il tenant. Ogni tabella operativa prende company_id NOT NULL con la
sequenza in tre passi (colonna nullable -> backfill -> vincolo), perché su un
database con dati una NOT NULL aggiunta di colpo fallisce.

Unica eccezione "user": company_id resta nullable, NULL significa utente fuori
da ogni company, cioè il super admin. È il vincolo che rende possibile la
feature, non una dimenticanza.

Il super admin NON viene creato qui: un valore nuovo di enum non è utilizzabile
nella stessa transazione che lo aggiunge, e una password in chiaro dentro una
migration non è una cosa da mandare in produzione. Va creato a parte, con
company_id NULL e la password nello stesso formato cifrato che usa il frontend.

Nota operativa: sono 24 tabelle riscritte riga per riga e altrettanti SET NOT
NULL in ACCESS EXCLUSIVE. Va eseguita in finestra di manutenzione, non a caldo.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '050'
down_revision: Union[str, None] = '049'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tabelle isolate per company. Restano fuori di proposito:
# - chatty: thread dell'assistente, non è dato di nessun cliente
# - carrier, collection_center: anagrafiche di soggetti esterni, condivise
# - dtr_document, fir_first_document, fir_fourth_document: raggiungibili solo
#   attraverso rae_product / disposal, che sono già isolati
TENANT_TABLES = (
  'collection_point',
  'constraints',
  'customer_group',
  'customer_rule',
  'customer_user_info',
  'delivery_group',
  'delivery_user_info',
  'disposal',
  'geographic_code',
  'geographic_zone',
  'history',
  'motivation',
  'order',
  'photo',
  'product',
  'rae_product',
  'rae_product_group',
  'schedule',
  'schedule_item',
  'schedule_item_collection_point',
  'schedule_item_order',
  'service',
  'service_user',
  'transport',
)

HISTORICAL_COMPANY = 'Ares Logistics'


def upgrade() -> None:
  op.create_table(
    'company',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
  )

  company_id = (
    op.get_bind()
    .execute(
      sa.text('INSERT INTO company (name, created_at, updated_at) VALUES (:name, now(), now()) RETURNING id'),
      {'name': HISTORICAL_COMPANY},
    )
    .scalar()
  )

  for table in TENANT_TABLES:
    op.add_column(table, sa.Column('company_id', sa.Integer(), nullable=True))
    op.execute(sa.text(f'UPDATE "{table}" SET company_id = {company_id}'))
    op.alter_column(table, 'company_id', nullable=False)
    op.create_foreign_key(f'fk_{table}_company_id', table, 'company', ['company_id'], ['id'])

  op.add_column('user', sa.Column('company_id', sa.Integer(), nullable=True))
  op.execute(sa.text(f'UPDATE "user" SET company_id = {company_id}'))
  op.create_foreign_key('fk_user_company_id', 'user', 'company', ['company_id'], ['id'])

  op.execute("ALTER TYPE userrole ADD VALUE 'SUPER_ADMIN';")


def downgrade() -> None:
  # Il valore di enum non si toglie: rimuovere un'etichetta da un enum in
  # PostgreSQL vuol dire ricreare il tipo e tutte le colonne che lo usano, e
  # 'SUPER_ADMIN' inutilizzato non fa danno.
  op.drop_constraint('fk_user_company_id', 'user', type_='foreignkey')
  op.drop_column('user', 'company_id')

  for table in reversed(TENANT_TABLES):
    op.drop_constraint(f'fk_{table}_company_id', table, type_='foreignkey')
    op.drop_column(table, 'company_id')

  op.drop_table('company')

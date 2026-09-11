"""delivery coverage calendar

Revision ID: 058
Revises: 057
Create Date: 2026-09-10 12:00:00.000000

Due tabelle nuove per la pagina a calendario della copertura dei corrieri:
i blocchi di schedulazione settimanale (giorno della settimana, veicolo,
fascia oraria) e i CAP coperti da ciascun blocco. Non più legate a un utente
delivery. Create dopo il tenant (050): company_id nasce NOT NULL, senza il
percorso nullable->backfill->vincolo che serve solo alle tabelle
preesistenti con dati.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '058'
down_revision: Union[str, None] = '057'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table(
    'delivery_coverage_entry',
    sa.Column('day_of_week', sa.Integer(), nullable=False),
    sa.Column('start_time', sa.Time(), nullable=False),
    sa.Column('end_time', sa.Time(), nullable=False),
    sa.Column('transport_id', sa.Integer(), nullable=False),
    sa.Column('company_id', sa.Integer(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['transport_id'], ['transport.id']),
    sa.ForeignKeyConstraint(['company_id'], ['company.id']),
    sa.PrimaryKeyConstraint('id'),
  )
  op.create_index(
    op.f('ix_delivery_coverage_entry_transport_id'), 'delivery_coverage_entry', ['transport_id'], unique=False
  )

  op.create_table(
    'delivery_coverage_cap',
    sa.Column('entry_id', sa.Integer(), nullable=False),
    sa.Column('cap', sa.String(), nullable=False),
    sa.Column('company_id', sa.Integer(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['entry_id'], ['delivery_coverage_entry.id']),
    sa.ForeignKeyConstraint(['company_id'], ['company.id']),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('entry_id', 'cap', name='uq_delivery_coverage_cap'),
  )
  op.create_index(op.f('ix_delivery_coverage_cap_entry_id'), 'delivery_coverage_cap', ['entry_id'], unique=False)


def downgrade() -> None:
  op.drop_index(op.f('ix_delivery_coverage_cap_entry_id'), table_name='delivery_coverage_cap')
  op.drop_table('delivery_coverage_cap')
  op.drop_index(op.f('ix_delivery_coverage_entry_transport_id'), table_name='delivery_coverage_entry')
  op.drop_table('delivery_coverage_entry')

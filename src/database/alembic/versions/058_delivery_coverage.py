"""delivery coverage calendar

Revision ID: 058
Revises: 057
Create Date: 2026-09-10 12:00:00.000000

Tre tabelle nuove per la pagina a calendario della copertura dei corrieri:
la copertura fissa (finestra di date), i suoi giorni della settimana con
fascia oraria e le assenze puntuali. Create dopo il tenant (050): company_id
nasce NOT NULL, senza il percorso nullable->backfill->vincolo che serve solo
alle tabelle preesistenti con dati.
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
    'delivery_coverage',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('end_date', sa.Date(), nullable=False),
    sa.Column('company_id', sa.Integer(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['user.id']),
    sa.ForeignKeyConstraint(['company_id'], ['company.id']),
    sa.PrimaryKeyConstraint('id'),
  )

  op.create_table(
    'delivery_coverage_day',
    sa.Column('day_of_week', sa.Integer(), nullable=False),
    sa.Column('start_time', sa.Time(), nullable=False),
    sa.Column('end_time', sa.Time(), nullable=False),
    sa.Column('coverage_id', sa.Integer(), nullable=False),
    sa.Column('company_id', sa.Integer(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['coverage_id'], ['delivery_coverage.id']),
    sa.ForeignKeyConstraint(['company_id'], ['company.id']),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('coverage_id', 'day_of_week', name='uq_delivery_coverage_day'),
  )
  op.create_index(op.f('ix_delivery_coverage_day_coverage_id'), 'delivery_coverage_day', ['coverage_id'], unique=False)

  op.create_table(
    'delivery_absence',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('end_date', sa.Date(), nullable=False),
    sa.Column('note', sa.String(), nullable=True),
    sa.Column('company_id', sa.Integer(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['user.id']),
    sa.ForeignKeyConstraint(['company_id'], ['company.id']),
    sa.PrimaryKeyConstraint('id'),
  )


def downgrade() -> None:
  op.drop_table('delivery_absence')
  op.drop_index(op.f('ix_delivery_coverage_day_coverage_id'), table_name='delivery_coverage_day')
  op.drop_table('delivery_coverage_day')
  op.drop_table('delivery_coverage')

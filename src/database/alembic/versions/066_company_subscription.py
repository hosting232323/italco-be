"""company automatic payment and subscription

Revision ID: 066
Revises: 065
Create Date: 2026-10-22 12:00:00.000000

Pagamento automatico per attività: il super admin accende il flag sulla company
(spento per tutte, nessun backfill) e un prezzo mensile (subscription_price_cents), poi
l'admin sottoscrive l'abbonamento Stripe dalla pagina di configurazione. Lo stato
dell'abbonamento sta in una tabella a parte, una riga per company.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '066'
down_revision: Union[str, None] = '065'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column(
    'company',
    sa.Column('automatic_payment', sa.Boolean(), nullable=False, server_default='false'),
  )
  op.add_column('company', sa.Column('subscription_price_cents', sa.Integer(), nullable=True))
  op.create_table(
    'company_subscription',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('company_id', sa.Integer(), nullable=False),
    sa.Column('stripe_customer_id', sa.String(), nullable=True),
    sa.Column('stripe_subscription_id', sa.String(), nullable=True),
    sa.Column('status', sa.String(), server_default='none', nullable=False),
    sa.Column('current_period_end', sa.DateTime(), nullable=True),
    sa.Column('cancel_at_period_end', sa.Boolean(), server_default='false', nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['company.id']),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('company_id'),
    sa.UniqueConstraint('stripe_customer_id'),
    sa.UniqueConstraint('stripe_subscription_id'),
  )


def downgrade() -> None:
  op.drop_table('company_subscription')
  op.drop_column('company', 'subscription_price_cents')
  op.drop_column('company', 'automatic_payment')

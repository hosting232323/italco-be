"""delivery user info -> transport

Revision ID: 058
Revises: 057
Create Date: 2026-09-10 12:00:00.000000

Collega l'utente delivery al suo veicolo. La cardinalita' e' molti-a-uno
(un utente un solo veicolo, un veicolo molti utenti), quindi basta una FK
nullable su delivery_user_info: nessun backfill, chi non e' assegnato resta
NULL.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '058'
down_revision: Union[str, None] = '057'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('delivery_user_info', sa.Column('transport_id', sa.Integer(), nullable=True))
  op.create_foreign_key(
    'fk_delivery_user_info_transport_id', 'delivery_user_info', 'transport', ['transport_id'], ['id']
  )


def downgrade() -> None:
  op.drop_constraint('fk_delivery_user_info_transport_id', 'delivery_user_info', type_='foreignkey')
  op.drop_column('delivery_user_info', 'transport_id')

"""veicolo assegnato all'ordine, coordinate del punto di ritiro

Revision ID: 066
Revises: 065
Create Date: 2026-09-25 12:00:00.000000

L'ordine ricordava solo la fascia oraria: quale veicolo l'aveva preso lo si
ricostruiva ripartendo virtualmente gli ordini della fascia, e la
pianificazione poi ne sceglieva uno a caso tra quelli con la stessa fascia e
gli stessi CAP. Ora il veicolo scelto alla creazione e' salvato sull'ordine e
borderò e capienza leggono la stessa cosa.

Il punto di ritiro salva le coordinate invece di geocodificare l'indirizzo a
ogni lettura della lista.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '066'
down_revision: Union[str, None] = '065'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('order', sa.Column('delivery_transport_id', sa.Integer(), nullable=True))
  op.create_foreign_key('order_delivery_transport_id_fkey', 'order', 'transport', ['delivery_transport_id'], ['id'])
  op.create_index('ix_order_delivery_transport_id', 'order', ['delivery_transport_id'])
  op.add_column('collection_point', sa.Column('lat', sa.Float(), nullable=True))
  op.add_column('collection_point', sa.Column('lon', sa.Float(), nullable=True))


def downgrade() -> None:
  op.drop_column('collection_point', 'lon')
  op.drop_column('collection_point', 'lat')
  op.drop_index('ix_order_delivery_transport_id', table_name='order')
  op.drop_constraint('order_delivery_transport_id_fkey', 'order', type_='foreignkey')
  op.drop_column('order', 'delivery_transport_id')

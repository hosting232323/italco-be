"""coordinate dell'indirizzo dell'ordine

Revision ID: 072
Revises: 071
Create Date: 2026-10-05 18:00:00.000000

L'indirizzo scelto dal menu Google nel form arriva con la sua posizione esatta:
salvarla evita di geocodificarlo di nuovo con Nominatim, che la stessa via
spesso la chiama in un altro modo e non la trova (l'ordine finiva fuori da ogni
zona di copertura). Vuote per gli ordini importati o scritti a mano, per cui
resta il geocoding.

address_lat/address_lon e non lat/lon: GET /order/<id> mette gia' lat/lon nel
payload, ed e' la posizione del corriere per il tracking.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '072'
down_revision: Union[str, None] = '071'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('order', sa.Column('address_lat', sa.Float(), nullable=True))
  op.add_column('order', sa.Column('address_lon', sa.Float(), nullable=True))


def downgrade() -> None:
  op.drop_column('order', 'address_lon')
  op.drop_column('order', 'address_lat')

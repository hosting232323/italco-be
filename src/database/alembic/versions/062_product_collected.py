"""product collected

Revision ID: 062
Revises: 061
Create Date: 2026-10-03 10:00:00.000000

Flag sul prodotto (non sull'ordine) che dice se è già stato ritirato al punto di
ritiro. Per ora lo si gestisce solo lato backend.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '062'
down_revision: Union[str, None] = '061'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('product', sa.Column('collected', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
  op.drop_column('product', 'collected')

"""Rae product quantity

Revision ID: 035
Revises: 034
Create Date: 2026-03-28 12:27:48.030242

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '035'
down_revision: Union[str, None] = '034'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('product', sa.Column('rae_product_quantity', sa.Integer(), nullable=True))


def downgrade() -> None:
  op.drop_column('product', 'rae_product_quantity')

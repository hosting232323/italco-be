"""link to rae product

Revision ID: 041
Revises: 040
Create Date: 2026-05-24 13:53:53.491107

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '041'
down_revision: Union[str, None] = '040'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('rae_product', sa.Column('link', sa.String(), nullable=False))


def downgrade() -> None:
  op.drop_column('rae_product', 'link')

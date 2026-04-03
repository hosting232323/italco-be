"""External link

Revision ID: 034
Revises: 033
Create Date: 2026-03-25 12:16:05.540958

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '034'
down_revision: Union[str, None] = '033'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('order', sa.Column('external_link', sa.String(), nullable=True))


def downgrade() -> None:
  op.drop_column('order', 'external_link')

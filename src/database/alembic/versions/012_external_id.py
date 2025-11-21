"""External id

Revision ID: 012
Revises: 011
Create Date: 2025-11-21 11:56:16.126543

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '012'
down_revision: Union[str, None] = '011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('order', sa.Column('external_id', sa.String(), nullable=True))


def downgrade() -> None:
  op.drop_column('order', 'external_id')

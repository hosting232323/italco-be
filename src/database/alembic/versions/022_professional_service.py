"""Professional service

Revision ID: 022
Revises: 021
Create Date: 2026-01-21 14:24:35.824594

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '022'
down_revision: Union[str, None] = '021'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('service', sa.Column('professional', sa.Boolean(), nullable=True))


def downgrade() -> None:
  op.drop_column('service', 'professional')

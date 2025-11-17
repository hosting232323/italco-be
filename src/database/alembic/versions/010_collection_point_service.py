"""Collection Point Service

Revision ID: 010
Revises: 009
Create Date: 2025-11-16 20:17:10.270781

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '010'
down_revision: Union[str, None] = '009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('collection_point', sa.Column('opening_time', sa.Time(), nullable=True))
  op.add_column('collection_point', sa.Column('closing_time', sa.Time(), nullable=True))
  op.add_column('service', sa.Column('duration', sa.Integer(), nullable=True))


def downgrade() -> None:
  op.drop_column('service', 'duration')
  op.drop_column('collection_point', 'closing_time')
  op.drop_column('collection_point', 'opening_time')

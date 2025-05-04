"""Order Photo

Revision ID: 9a7653083b81
Revises: 0bc21c77146a
Create Date: 2025-05-04 13:01:39.149205

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9a7653083b81'
down_revision: Union[str, None] = '0bc21c77146a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('order', sa.Column('photo', sa.LargeBinary(), nullable=True))
  op.add_column('order', sa.Column('photo_mime_type', sa.String(), nullable=True))


def downgrade() -> None:
  op.drop_column('order', 'photo_mime_type')
  op.drop_column('order', 'photo')

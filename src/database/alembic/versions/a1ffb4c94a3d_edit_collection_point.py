"""edit collection point

Revision ID: a1ffb4c94a3d
Revises: c8dc7480805d
Create Date: 2025-06-27 12:04:28.488826

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1ffb4c94a3d'
down_revision: Union[str, None] = 'c8dc7480805d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('collection_point', 'province')
    op.drop_column('collection_point', 'city')


def downgrade() -> None:
    op.add_column('collection_point', sa.Column('city', sa.VARCHAR(), autoincrement=False, nullable=False))
    op.add_column('collection_point', sa.Column('province', sa.VARCHAR(), autoincrement=False, nullable=False))

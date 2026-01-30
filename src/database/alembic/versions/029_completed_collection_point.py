"""completed collection point

Revision ID: 029
Revises: 028
Create Date: 2026-02-19 16:45:50.483622

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '029'
down_revision: Union[str, None] = '028'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('schedule_item_collection_point', sa.Column('completed', sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column('schedule_item_collection_point', 'completed')

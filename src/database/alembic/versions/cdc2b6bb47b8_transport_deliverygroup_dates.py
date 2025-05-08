"""Transport DeliveryGroup Dates

Revision ID: cdc2b6bb47b8
Revises: 560f730b9de1
Create Date: 2025-05-07 18:23:31.996533

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'cdc2b6bb47b8'
down_revision: Union[str, None] = '560f730b9de1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('transport_delivery_group', sa.Column('start_date', sa.Date(), nullable=False))
  op.add_column('transport_delivery_group', sa.Column('end_date', sa.Date(), nullable=True))
  op.drop_column('transport_delivery_group', 'start')
  op.drop_column('transport_delivery_group', 'end')


def downgrade() -> None:
  op.add_column('transport_delivery_group', sa.Column('end', sa.DATE(), autoincrement=False, nullable=True))
  op.add_column('transport_delivery_group', sa.Column('start', sa.DATE(), autoincrement=False, nullable=False))
  op.drop_column('transport_delivery_group', 'end_date')
  op.drop_column('transport_delivery_group', 'start_date')

"""Order Dates

Revision ID: 9e41332d47d6
Revises: 9a7653083b81
Create Date: 2025-05-05 17:05:43.744372

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9e41332d47d6'
down_revision: Union[str, None] = '9a7653083b81'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('order', sa.Column('booking_date', sa.Date(), nullable=True))
  op.add_column('order', sa.Column('assignament_date', sa.Date(), nullable=True))


def downgrade() -> None:
  op.drop_column('order', 'assignament_date')
  op.drop_column('order', 'booking_date')

"""new dates

Revision ID: 027
Revises: 026
Create Date: 2026-02-12 12:46:30.526328

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '027'
down_revision: Union[str, None] = '026'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.alter_column('order', 'booking_date', new_column_name='completion_date')
  op.add_column('order', sa.Column('confirmation_date', sa.Date(), nullable=True))
  op.add_column('order', sa.Column('booking_date', sa.Date(), nullable=True))


def downgrade() -> None:
  op.drop_column('order', 'booking_date')
  op.drop_column('order', 'confirmation_date')
  op.alter_column('order', 'completion_date', new_column_name='booking_date')

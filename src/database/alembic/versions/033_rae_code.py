"""Rae code

Revision ID: 033
Revises: 032
Create Date: 2026-03-21 11:00:38.649523

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '033'
down_revision: Union[str, None] = '032'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('customer_user_info', sa.Column('rae_code', sa.String(), nullable=True))
  op.alter_column('customer_user_info', 'code', new_column_name='import_code')


def downgrade() -> None:
  op.alter_column('customer_user_info', 'import_code', new_column_name='code')
  op.drop_column('customer_user_info', 'rae_code')

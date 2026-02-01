"""Customer code

Revision ID: 024
Revises: 023
Create Date: 2026-02-01 07:02:58.940995

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '024'
down_revision: Union[str, None] = '023'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('customer_user_info', sa.Column('code', sa.String(), nullable=True))


def downgrade() -> None:
  op.drop_column('customer_user_info', 'code')

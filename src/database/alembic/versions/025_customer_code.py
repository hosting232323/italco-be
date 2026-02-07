"""Customer code

Revision ID: 025
Revises: 024
Create Date: 2026-02-01 07:02:58.940995

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '025'
down_revision: Union[str, None] = '024'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('customer_user_info', sa.Column('code', sa.String(), nullable=True))
  op.alter_column('product', 'service_user_id', existing_type=sa.INTEGER(), nullable=True)


def downgrade() -> None:
  op.alter_column('product', 'service_user_id', existing_type=sa.INTEGER(), nullable=False)
  op.drop_column('customer_user_info', 'code')

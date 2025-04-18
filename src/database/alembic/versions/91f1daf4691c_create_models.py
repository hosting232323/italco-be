"""Create models

Revision ID: 91f1daf4691c
Revises: 
Create Date: 2025-04-18 18:35:41.223949

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '91f1daf4691c'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table('italco_user',
    sa.Column('role', sa.Enum('ADMIN', 'CUSTOMER', 'OPERATOR', 'DELIVERY', name='userrole'), nullable=False),
    sa.Column('password', sa.String(), nullable=True),
    sa.Column('pass_token', sa.String(), nullable=True),
    sa.Column('email', sa.String(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
  )


def downgrade() -> None:
  op.drop_table('italco_user')
  filetype_enum = sa.Enum('ADMIN', 'CUSTOMER', 'OPERATOR', 'DELIVERY', name='userrole')
  filetype_enum.drop(op.get_bind(), checkfirst=True)

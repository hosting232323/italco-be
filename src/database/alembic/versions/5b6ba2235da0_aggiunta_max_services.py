"""Aggiunta max services

Revision ID: 5b6ba2235da0
Revises: 426c422f6e50
Create Date: 2025-07-10 11:45:03.669909

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '5b6ba2235da0'
down_revision: Union[str, None] = '426c422f6e50'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('service', sa.Column('max_services', sa.Integer(), nullable=True))


def downgrade() -> None:
  op.drop_column('service', 'max_services')

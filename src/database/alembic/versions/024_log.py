"""Log

Revision ID: 024
Revises: 023
Create Date: 2026-01-17 17:26:16.900939

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '024'
down_revision: Union[str, None] = '023'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table(
    'log',
    sa.Column('content', sa.String(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(
      ['user_id'],
      ['user.id'],
    ),
    sa.PrimaryKeyConstraint('id'),
  )


def downgrade() -> None:
  op.drop_table('log')

"""Dedicated random tokens for public order tracking.

Revision ID: 061
Revises: 060
Create Date: 2026-09-26 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '061'
down_revision: Union[str, None] = '060'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table(
    'order_tracking_token',
    sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
    sa.Column('company_id', sa.Integer(), sa.ForeignKey('company.id'), nullable=False),
    sa.Column(
      'order_id',
      sa.Integer(),
      sa.ForeignKey('order.id', ondelete='CASCADE'),
      nullable=False,
    ),
    sa.Column('token_hash', sa.String(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.UniqueConstraint('token_hash', name='uq_order_tracking_token_token_hash'),
  )


def downgrade() -> None:
  op.drop_table('order_tracking_token')

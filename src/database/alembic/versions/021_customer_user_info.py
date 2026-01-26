"""Customer User Info

Revision ID: 021
Revises: 020
Create Date: 2026-01-25 11:16:21.027214

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '021'
down_revision: Union[str, None] = '020'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table(
    'customer_user_info',
    sa.Column('city', sa.String(), nullable=False),
    sa.Column('address', sa.String(), nullable=False),
    sa.Column('tax_code', sa.String(), nullable=False),
    sa.Column('company_name', sa.String(), nullable=False),
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
  op.add_column('rae_product', sa.Column('cer_code', sa.Integer(), nullable=False))
  op.add_column('rae_product', sa.Column('group_code', sa.String(), nullable=False))
  op.drop_column('rae_product', 'code')


def downgrade() -> None:
  op.add_column('rae_product', sa.Column('code', sa.INTEGER(), autoincrement=False, nullable=False))
  op.drop_column('rae_product', 'group_code')
  op.drop_column('rae_product', 'cer_code')
  op.drop_table('customer_user_info')

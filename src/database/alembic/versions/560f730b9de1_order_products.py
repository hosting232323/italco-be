"""Order Products

Revision ID: 560f730b9de1
Revises: 9e41332d47d6
Create Date: 2025-05-07 14:01:31.333872

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '560f730b9de1'
down_revision: Union[str, None] = '9e41332d47d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.drop_table('order_product')
  op.drop_table('product')
  op.add_column('order', sa.Column('products', postgresql.ARRAY(sa.String()), nullable=True))


def downgrade() -> None:
  op.drop_column('order', 'products')
  op.create_table('order_product',
    sa.Column('order_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('product_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['order_id'], ['order.id'], name='order_product_order_id_fkey'),
    sa.ForeignKeyConstraint(['product_id'], ['product.id'], name='order_product_product_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='order_product_pkey')
  )
  op.create_table('product',
    sa.Column('name', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('description', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('user_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['italco_user.id'], name='product_user_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='product_pkey')
  )

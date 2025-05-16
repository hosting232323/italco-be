"""Product and Addressee refactor

Revision ID: 20306de2eff9
Revises: 4838acea2c68
Create Date: 2025-05-15 20:16:57.110862

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '20306de2eff9'
down_revision: Union[str, None] = '4838acea2c68'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.drop_constraint('fk_order_addressee', 'order', type_='foreignkey')
  op.drop_column('order', 'addressee_id')
  op.drop_column('order', 'products')
  op.drop_table('addressee')
  op.add_column('order', sa.Column('addressee', sa.String(), nullable=False))
  op.add_column('order', sa.Column('address', sa.String(), nullable=False))
  op.add_column('order', sa.Column('cap', sa.String(), nullable=False))
  op.add_column('order_service_user', sa.Column('product', sa.String(), nullable=False))
  op.add_column('service', sa.Column('type', sa.Enum('DELIVERY', 'WITHDRAW', 'REPLACEMENT', 'CHECK', name='ordertype'), nullable=False))


def downgrade() -> None:
  op.create_table('addressee',
    sa.Column('name', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('address', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('city', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('cap', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('province', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('user_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['italco_user.id'], name='addressee_user_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='addressee_pkey')
  )
  op.drop_column('order_service_user', 'product')
  op.add_column('order', sa.Column('products', postgresql.ARRAY(sa.VARCHAR()), autoincrement=False, nullable=True))
  op.add_column('order', sa.Column('addressee_id', sa.INTEGER(), autoincrement=False, nullable=False))
  op.create_foreign_key('fk_order_addressee', 'order', 'addressee', ['addressee_id'], ['id'])
  op.drop_column('order', 'cap')
  op.drop_column('order', 'address')
  op.drop_column('order', 'addressee')
  op.drop_column('service', 'type')

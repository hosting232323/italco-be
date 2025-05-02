"""Product and Order Type

Revision ID: 0bc21c77146a
Revises: 9be887cb08f1
Create Date: 2025-04-30 15:17:35.310329

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0bc21c77146a'
down_revision: Union[str, None] = '9be887cb08f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table('product',
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('description', sa.String(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['italco_user.id'], ),
    sa.PrimaryKeyConstraint('id')
  )
  op.create_table('order_product',
    sa.Column('order_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['order_id'], ['order.id'], ),
    sa.ForeignKeyConstraint(['product_id'], ['product.id'], ),
    sa.PrimaryKeyConstraint('id')
  )
  op.create_table('order_service_user',
    sa.Column('order_id', sa.Integer(), nullable=False),
    sa.Column('service_user_id', sa.Integer(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['order_id'], ['order.id'], ),
    sa.ForeignKeyConstraint(['service_user_id'], ['service_user.id'], ),
    sa.PrimaryKeyConstraint('id')
  )
  order_type_enum = sa.Enum('DELIVERY', 'WITHDRAW', 'REPLACEMENT', 'CHECK', name='ordertype')
  order_type_enum.create(op.get_bind())
  op.add_column('order', sa.Column('type', order_type_enum, nullable=True))
  op.execute('UPDATE "order" SET type = \'DELIVERY\'')
  op.alter_column('order', 'type', nullable=False)
  sa.Enum('PENDING', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED', 'ANOMALY', 'DELAY', name='orderstatus_new').create(op.get_bind())
  op.execute('ALTER TABLE "order" ALTER COLUMN status TYPE orderstatus_new USING status::text::orderstatus_new')
  sa.Enum('PENDING', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED', 'ANOMALY', name='orderstatus').drop(op.get_bind(), checkfirst=True)
  op.execute('ALTER TYPE orderstatus_new RENAME TO orderstatus')
  op.drop_constraint('order_service_user_id_fkey', 'order', type_='foreignkey')
  op.drop_column('order', 'service_user_id')


def downgrade() -> None:
  op.add_column('order', sa.Column('service_user_id', sa.INTEGER(), autoincrement=False, nullable=False))
  op.create_foreign_key('order_service_user_id_fkey', 'order', 'service_user', ['service_user_id'], ['id'])
  op.drop_column('order', 'type')
  op.drop_table('order_service_user')
  op.drop_table('order_product')
  op.drop_table('product')
  filetype_enum = sa.Enum('DELIVERY', 'WITHDRAW', 'REPLACEMENT', 'CHECK', name='ordertype')
  filetype_enum.drop(op.get_bind(), checkfirst=True)

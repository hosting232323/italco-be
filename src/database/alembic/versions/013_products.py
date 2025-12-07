"""Products

Revision ID: 013
Revises: 012
Create Date: 2025-11-28 11:49:03.827026
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '013'
down_revision: Union[str, None] = '012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.rename_table('order_service_user', 'product')
  op.alter_column('product', 'product', new_column_name='name', existing_type=sa.VARCHAR(), nullable=False)
  op.add_column('product', sa.Column('collection_point_id', sa.Integer(), nullable=True))
  op.execute("""
    UPDATE product p
    SET collection_point_id = o.collection_point_id
    FROM "order" o
    WHERE p.order_id = o.id;
  """)
  op.alter_column('product', 'collection_point_id', nullable=False)
  op.create_foreign_key(
    'product_collection_point_id_fkey', 'product', 'collection_point', ['collection_point_id'], ['id']
  )

  op.drop_constraint(op.f('order_collection_point_id_fkey'), 'order', type_='foreignkey')
  op.drop_column('order', 'collection_point_id')


def downgrade() -> None:
  op.add_column('order', sa.Column('collection_point_id', sa.INTEGER(), nullable=True))
  op.execute("""
    UPDATE "order" o
    SET collection_point_id = p.collection_point_id
    FROM product p
    WHERE p.order_id = o.id;
  """)
  op.alter_column('order', 'collection_point_id', nullable=False)
  op.create_foreign_key(
    op.f('order_collection_point_id_fkey'), 'order', 'collection_point', ['collection_point_id'], ['id']
  )

  op.drop_constraint('product_collection_point_id_fkey', 'product', type_='foreignkey')
  op.drop_column('product', 'collection_point_id')
  op.alter_column('product', 'name', new_column_name='product', existing_type=sa.VARCHAR(), nullable=False)
  op.rename_table('product', 'order_service_user')

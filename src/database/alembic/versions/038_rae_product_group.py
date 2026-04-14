"""Rae Product Group

Revision ID: 038
Revises: 037
Create Date: 2026-04-14 09:55:28.915985

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '038'
down_revision: Union[str, None] = '037'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.rename_table('rae_product', 'rae_product_group')

  op.create_table(
    'rae_product',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=True, server_default='1'),
    sa.Column('cancellations', sa.Integer(), nullable=True, server_default='0'),
    sa.Column(
      'status', sa.Enum('GENERATED', 'EMITTED', 'LDR', 'DISPOSED_OFF', 'ANNULLED', name='raestatus'), nullable=False
    ),
    sa.Column('rae_product_group_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['rae_product_group_id'], ['rae_product_group.id']),
    sa.PrimaryKeyConstraint('id'),
  )

  op.execute("""
    INSERT INTO rae_product (quantity, cancellations, status, rae_product_group_id)
    SELECT
      p.rae_product_quantity,
      0,
      'GENERATED',
      p.rae_product_id
    FROM product p
    WHERE p.rae_product_id IS NOT NULL
  """)
  op.drop_constraint('product_rae_product_id_fkey', 'product', type_='foreignkey')
  op.execute("""
    UPDATE product p
    SET rae_product_id = rp.id
    FROM rae_product rp
    WHERE rp.rae_product_group_id = p.rae_product_id
  """)

  op.create_foreign_key('product_rae_product_id_fkey', 'product', 'rae_product', ['rae_product_id'], ['id'])
  op.drop_column('product', 'rae_product_quantity')


def downgrade() -> None:
  op.drop_constraint('product_rae_product_id_fkey', 'product', type_='foreignkey')
  op.drop_table('rae_product')
  op.rename_table('rae_product_group', 'rae_product')
  op.add_column('rae_product', sa.Column('cer_code', sa.INTEGER(), nullable=False))
  op.add_column('rae_product', sa.Column('group_code', sa.VARCHAR(), nullable=False))
  op.add_column('rae_product', sa.Column('name', sa.VARCHAR(), nullable=False))
  op.create_foreign_key('product_rae_product_id_fkey', 'product', 'rae_product', ['rae_product_id'], ['id'])
  op.add_column('product', sa.Column('rae_product_quantity', sa.INTEGER(), nullable=True))
